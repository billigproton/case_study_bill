from knowledge_graph import resolve

# ---------------------------------------------------------------------------
# 4. OTESTOVÁNÍ JEDNODUCHÉHO KNOWLEDGE GRAPH
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_questions = [
        "How do Oxbridge universities compare in career prospects in 2015?",
        "Compare UCL and LSE overall scores."
    ]

    print("=== Knowledge Graph Disambiguation Demo ===\n")
    for q in test_questions:
        resolved, notes = resolve(q)
        print(f"INPUT:    {q}")
        print(f"RESOLVED: {resolved}")
        for note in notes:
            print(f"          🔍 {note}")
        print()