import json
import os
import re
import sqlite3
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv
from openai import AzureOpenAI

from knowledge_graph import resolve

load_dotenv()

client = AzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
)
DEPLOYMENT_NAME = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]

# Cesta k SQLite databázi vytvořené skriptem build_database.py
DB_PATH = Path(__file__).resolve().parent / "guardian_rankings.db"

# Cesta k JSON souboru, do kterého se bokem loguje každá interakce (otázka, SQL, odpověď)
LOG_PATH = Path(__file__).resolve().parent / "qa_log.json"

# Cesta k semantic layer YAML souboru - byznysový popis tabulek, joinů, dimenzí,
# metrik a jejich omezení
SEMANTIC_LAYER_PATH = Path(__file__).resolve().parent / "semantic_layer.yml"

# Bezpečnostní pojistka - LLM smí generovat pouze SELECT dotazy, nikdy neupravuje data/schéma
FORBIDDEN_SQL_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create",
    "attach", "detach", "pragma", "replace", "vacuum",
)


def get_db_schema() -> str:
    """Vrátí CREATE TABLE definice všech tabulek v DB, aby LLM znal dostupné sloupce a názvy tabulek."""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        conn.close()
    return "\n\n".join(row[0] for row in rows if row[0])


# Schéma se načte jednou při startu a znovu použije při každém dotazu uživatele
DB_SCHEMA = get_db_schema()


def get_semantic_layer() -> str:
    """Načte obsah semantic_layer.yml - byznysový kontext k datům (významy sloupců, joiny,
    omezení), který LLM přečte jako první krok, než začne generovat SQL dotaz."""
    return SEMANTIC_LAYER_PATH.read_text(encoding="utf-8")


# Stejně jako schéma DB se i semantic layer načte jednou při startu aplikace
SEMANTIC_LAYER = get_semantic_layer()


def ask_llm(messages: list[dict]) -> str:
    """Zavolá Azure OpenAI chat completion se zadanými zprávami a vrátí text odpovědi."""
    completion = client.chat.completions.create(
        model=DEPLOYMENT_NAME,
        messages=messages,
        temperature=0.7,
        max_completion_tokens=800,
        top_p=0.95,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None,
    )
    return completion.choices[0].message.content.strip()


def extract_sql(raw_text: str) -> str:
    """Odstraní případný markdown code fence (```sql ... ```) okolo SQL vygenerovaného LLM."""
    match = re.search(r"```(?:sql)?\s*(.*?)```", raw_text, re.DOTALL | re.IGNORECASE)
    sql = match.group(1) if match else raw_text
    return sql.strip().rstrip(";")


def is_safe_select(sql: str) -> bool:
    """Povolí spuštění pouze dotazů začínajících SELECT a bez zakázaných klíčových slov."""
    lowered = sql.lower().lstrip()
    if not lowered.startswith("select"):
        return False
    return not any(re.search(rf"\b{keyword}\b", lowered) for keyword in FORBIDDEN_SQL_KEYWORDS)


def generate_sql(question: str) -> str:
    """Krok 1: LLM si nejprve přečte semantic_layer.yml (byznysový kontext k datům), poté se
    otázka doplní o kontext z knowledge_graph.py (kanonické názvy institucí / rozbalení skupin)
    a teprve poté proces pokračuje generováním SQL dotazu."""
    resolved_question, kg_notes = resolve(question)
    system_prompt = (
        "You are an assistant that translates natural-language questions into SQL queries for a "
        "SQLite database containing The Guardian's UK university rankings (2013-2015).\n\n"
        "First, study the semantic description of the data (column meanings, joins between "
        "tables, and their caveats/limitations):\n"
        f"{SEMANTIC_LAYER}\n\n"
        f"Technical database schema:\n{DB_SCHEMA}\n\n"
        "Next, consider the knowledge graph disambiguation of the question, which resolves "
        "institution nicknames/full names and group names (e.g. 'Oxbridge', 'Russell Group') to "
        "the exact institution names as stored in the database:\n"
        f"- Original question: {question}\n"
        f"- Disambiguated question: {resolved_question}\n"
        f"- Disambiguation notes: {'; '.join(kg_notes)}\n\n"
        "Rules:\n"
        "- Follow the caveats and recommendations from the semantic description above (e.g. the "
        "fan_out_warning on joins, which columns can/cannot be aggregated).\n"
        "- When filtering by institution, use the exact canonical name(s) from the disambiguated "
        "question/notes above rather than the name(s) as they appear in the original question.\n"
        "- Respond with ONLY the raw SQL query, no explanation and no markdown code blocks.\n"
        "- Use SELECT statements exclusively (no INSERT/UPDATE/DELETE/DDL statements).\n"
        "- If the query does not return an aggregated result, limit the number of rows with LIMIT."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    return extract_sql(ask_llm(messages))


def run_sql(sql: str) -> tuple[list[str], list[tuple]]:
    """Krok 2: spustí SQL dotaz proti databázi v režimu pouze pro čtení (mode=ro)."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cursor = conn.execute(sql)
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchmany(200)  # pojistka proti extrémně velkému výsledku
    finally:
        conn.close()
    return columns, rows


def format_results(columns: list[str], rows: list[tuple]) -> str:
    """Naformátuje výsledek SQL dotazu do jednoduché textové tabulky, kterou pošleme LLM."""
    if not rows:
        return "(the query returned no rows)"
    header = " | ".join(columns)
    lines = [header, "-" * len(header)]
    lines.extend(" | ".join(str(value) for value in row) for row in rows)
    return "\n".join(lines)


def log_interaction(question: str, sql_code: str, answer: str) -> None:
    """Připojí záznam {question, sql_code, answer} do JSON souboru s historií všech interakcí."""
    if LOG_PATH.exists():
        try:
            log_data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log_data = []
    else:
        log_data = []

    log_data.append({"question": question, "sql_code": sql_code, "answer": answer})
    LOG_PATH.write_text(json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_answer(question: str, sql: str, result_text: str) -> str:
    """Krok 3: výsledek SQL dotazu spolu se sémantickým popisem dat pošleme zpět LLM, který z nich
    sestaví odpověď v přirozeném jazyce a případně upozorní na relevantní omezení (caveat)."""
    system_prompt = (
        "You are the 'Guardian University Guide' English speaking assistant, answering questions about UK "
        "university rankings (2013-2015). You will receive a semantic description of the data, "
        "a SQL query, and its result from the database - use them to answer the user concisely "
        "and in natural language. If relevant to the question, mention an important caveat/"
        "limitation of the metric from the semantic description. If the result contains no data, "
        "tell the user so.\n\n"
        f"Semantic description of the data:\n{SEMANTIC_LAYER}"
    )
    user_prompt = (
        f"User question: {question}\n\n"
        f"SQL query used:\n{sql}\n\n"
        f"Query result:\n{result_text}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return ask_llm(messages)


def answer_question(question: str) -> str:
    """Hlavní pipeline volaná Gradio rozhraním: otázka -> SQL -> výsledek z DB -> odpověď LLM.

    Každá interakce se navíc bokem zaloguje do JSON souboru (viz log_interaction)."""
    try:
        sql = generate_sql(question)
    except Exception as exc:
        answer = f"Failed to generate a SQL query: {exc}"
        log_interaction(question, None, answer)
        return answer

    if not is_safe_select(sql):
        answer = f"The generated query was not allowed for safety reasons:\n{sql}"
        log_interaction(question, sql, answer)
        return answer

    try:
        columns, rows = run_sql(sql)
    except sqlite3.Error as exc:
        answer = f"The generated SQL query failed ({exc}):\n{sql}"
        log_interaction(question, sql, answer)
        return answer

    result_text = format_results(columns, rows)
    answer = generate_answer(question, sql, result_text)
    log_interaction(question, sql, answer)
    return answer


# Vytvoření Gradio rozhraní
iface = gr.Interface(
    fn=answer_question,
    inputs=gr.Textbox(placeholder="Enter your question here"),
    outputs=gr.Textbox(),
    title="University League Helper",
    description="Examples of questions to ask:\n1. Which unversity ranks 2nd in student to staff ratio?\n2. Explain to me the meaning of the metric average entry tariff\n3. How is Oxbridge doing in the overall rating in 2013? How is accounting and finance subject ranked?"
)

# Spuštění rozhraní (pouze při přímém spuštění skriptu, ne při importu např. z testů)
if __name__ == "__main__":
    iface.launch()
