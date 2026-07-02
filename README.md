# League Data Case Study

## O repozitáři

Tento repozitář obsahuje moje řešení zadání **Guardian University League Data Case Study**. Cílem je zpracovat data
žebříčků britských univerzit The Guardian (2013–2015) do relační podoby a nad nimi postavit
chatbota, který na základě dotazu v přirozeném jazyce vygeneruje SQL dotaz, vykoná ho nad daty
a vrátí uživateli srozumitelnou odpověď.

Samotný přístup k řešení je zmíněn v přiložené prezentaci (viz sekce Můj přístup k řešení)

## Soubory a jejich význam

| Soubor / složka | Význam |
|---|---|
| `source_data/` | Zdrojová data — originální Excel sešit The Guardian s žebříčky univerzit (2013–2015). |
| `build_database.py` | Načte zdrojový Excel sešit a převede jeho listy do relační SQLite databáze (`guardian_rankings.db`), včetně vytvoření indexů a transformace datových typů (sekce „transformace“). |
| `guardian_rankings.db` | Výsledná SQLite databáze vygenerovaná skriptem `build_database.py` (tabulky `guardian_ranking` a `guardian_subject_areas`). |
| `semantic_layer.yml` | Sémantický popis dat — významy tabulek, sloupců, joinů a jejich omezení (caveaty). Slouží jako kontext pro LLM při generování SQL dotazů. |
| `knowledge_graph.py` | Jednoduchý knowledge graph pro disambiguaci názvů univerzit a skupinových aliasů (např. „Oxbridge“) před předáním otázky generátoru SQL. |
| `knowledge_graph_test.py` | Ukázkové otestování funkce `resolve()` z `knowledge_graph.py`. |
| `chatbot_ui.py` | Hlavní aplikace — Gradio rozhraní, které dotaz uživatele postupně obohatí o sémantický popis dat a kontext z knowledge graphu, nechá LLM (Azure OpenAI) vygenerovat SQL dotaz, spustí ho nad databází a výsledek pošle zpět LLM pro finální odpověď. Každá interakce se loguje do `qa_log.json`. |
| `qa_log.json` | Log všech interakcí s chatbotem (otázka, vygenerovaný SQL dotaz, odpověď). |
| `tests.ipynb` | Jupyter notebook s testy a průzkumem dat při přípravě relační databáze (např. ověření unikátnosti primárních klíčů). |
| `League Data entity relationship diagram.drawio` | Entity-relationship diagram (ERD) datového modelu dat převedených do relační struktury |
| `.env` | Lokální konfigurace (přístupové údaje k Azure OpenAI) — není součástí repozitáře (viz `.gitignore`). |
| `.gitignore` | Vynechává citlivé a generované soubory (`.env`, `__pycache__` apod.) z verzování. |

## Můj přístup k řešení

Prezentace shrnující můj přístup k řešení *[(League Data Case Study: My Approach)](https://1drv.ms/p/c/f9b898b51413f654/IQAMn3rKRSWSTbUSMs6uTQBJAZ-elC3SFrTFsRg7HjoqkjY?e=TjB1M6)*
