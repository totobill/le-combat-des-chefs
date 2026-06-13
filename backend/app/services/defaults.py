DEFAULT_SCORING = {
    "mdp": {"points_per_word": 2, "placement": {"1": 20, "2": 12, "3": 6}},
    "dcc": {"duo": 1, "carre": 3, "cash": 6, "placement": {"1": 10, "2": 6, "3": 3}},
    "chips": {
        "points_per_correct": 1,
        "placement": {"1": 15, "2": 10, "3": 5},
        "malus_per_wrong": 1,
    },
    "molkky": {"placement": {"1": 25, "2": 15, "3": 8}},
    "paroles": {"points_per_word": 1},
    "piscine": {"placement": {"1": 20, "2": 12, "3": 6}},
    "poignards": {"handicap_seconds": {"1": 0, "2": 15, "3": 30}},
}

DEFAULT_TEAMS = [
    {"name": "Équipe A", "color": "#5b5ef5"},
    {"name": "Équipe B", "color": "#f59e0b"},
    {"name": "Équipe C", "color": "#10b981"},
]

DEFAULT_DCC_QUESTIONS = [
    {
        "question": "L'eau bout à quelle température au niveau de la mer ?",
        "category": "Culture générale",
        "duo_opts": ["80°C", "100°C"],
        "duo_correct": 1,
        "carre_opts": ["90°C", "95°C", "100°C", "110°C"],
        "carre_correct": 2,
        "cash_answer": "100",
        "cash_aliases": ["100°C", "100 degrees"],
    },
    {
        "question": "En quelle année la France a-t-elle gagné la Coupe du Monde ?",
        "category": "Sport",
        "duo_opts": ["1998", "2002"],
        "duo_correct": 0,
        "carre_opts": ["1994", "1998", "2002", "2006"],
        "carre_correct": 1,
        "cash_answer": "1998",
        "cash_aliases": [],
    },
    {
        "question": "Que signifie VPN ?",
        "category": "Informatique",
        "duo_opts": ["Virtual Private Network", "Very Public Network"],
        "duo_correct": 0,
        "carre_opts": [
            "Virus Protection Network",
            "Virtual Private Network",
            "Variable Protocol Node",
            "Verified Personal Name",
        ],
        "carre_correct": 1,
        "cash_answer": "Virtual Private Network",
        "cash_aliases": ["VPN"],
    },
]

DEFAULT_MDP_WORDS = [
    "ordinateur",
    "spatule",
    "parapluie",
    "bibliothèque",
    "téléphone",
    "croissant",
    "montagne",
    "cinéma",
]

DEFAULT_PAROLES = [
    {
        "title": "Exemple — J'aime les gens",
        "audio_url": "",
        "display_text": "J'aime ___ gens que je ___ vois",
        "answers": ["les", "ne"],
    },
]

DEFAULT_CHIPS = [
    {
        "name": "Chips nature",
        "flavors": ["pomme de terre", "sel", "huile"],
    },
    {
        "name": "Chips paprika",
        "flavors": ["pomme de terre", "paprika", "sel", "fumée"],
    },
]

PROGRAM_MODULES = [
    {"id": "mdp", "label": "Mot de Passe", "phase": "solo", "icon": "🎭"},
    {"id": "dcc", "label": "Duo / Carré / Cash", "phase": "solo", "icon": "🎯"},
    {"id": "chips", "label": "Chips", "phase": "solo", "icon": "🥔"},
    {"id": "molkky", "label": "Mölkky", "phase": "duo", "icon": "🎳"},
    {"id": "paroles", "label": "N'oubliez pas les paroles", "phase": "groupe", "icon": "🎵"},
    {"id": "piscine", "label": "Piscine — Relais", "phase": "groupe", "icon": "🏊"},
    {"id": "poignards", "label": "Épreuve des poignards", "phase": "finale", "icon": "🔪"},
]
