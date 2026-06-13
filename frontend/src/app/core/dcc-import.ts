export interface DccImportQuestion {
  question: string;
  category: string;
  duo: [string, string];
  duo_correct: number;
  carre: [string, string, string, string];
  carre_correct: number;
  cash: string;
  cash_aliases?: string[];
}

export interface DccImportFile {
  format: 'combat-des-chefs-dcc';
  version: 1;
  instructions: string;
  questions: DccImportQuestion[];
}

export interface DccImportRow {
  question: string;
  category: string;
  duo_opts: [string, string];
  duo_correct: number;
  carre_opts: [string, string, string, string];
  carre_correct: number;
  cash_answer: string;
  cash_aliases: string[];
}

const INSTRUCTIONS =
  'Remplissez chaque objet questions[]. ' +
  'duo = exactement 2 propositions. duo_correct = 0 (1re) ou 1 (2e). ' +
  'carre = exactement 4 propositions. carre_correct = 0 à 3. ' +
  'cash = réponse libre attendue. cash_aliases = variantes acceptées (optionnel).';

const EMPTY_EXAMPLE: DccImportQuestion = {
  question: 'Quelle est la capitale de la France ?',
  category: 'Géographie',
  duo: ['Paris', 'Lyon'],
  duo_correct: 0,
  carre: ['Paris', 'Lyon', 'Marseille', 'Bordeaux'],
  carre_correct: 0,
  cash: 'Paris',
  cash_aliases: [],
};

const BLANK_EXAMPLE: DccImportQuestion = {
  question: '',
  category: 'Culture générale',
  duo: ['', ''],
  duo_correct: 0,
  carre: ['', '', '', ''],
  carre_correct: 0,
  cash: '',
  cash_aliases: [],
};

export function dccImportTemplate(count = 5): DccImportFile {
  const questions = [EMPTY_EXAMPLE, ...Array.from({ length: count - 1 }, () => ({ ...BLANK_EXAMPLE, duo: ['', ''] as [string, string], carre: ['', '', '', ''] as [string, string, string, string] }))];
  return {
    format: 'combat-des-chefs-dcc',
    version: 1,
    instructions: INSTRUCTIONS,
    questions,
  };
}

export function dccExportFromDb(
  rows: {
    question: string;
    category: string;
    duo_opts: string[];
    duo_correct: number;
    carre_opts: string[];
    carre_correct: number;
    cash_answer: string;
    cash_aliases?: string[];
  }[],
): DccImportFile {
  return {
    format: 'combat-des-chefs-dcc',
    version: 1,
    instructions: INSTRUCTIONS,
    questions: rows.map((r) => ({
      question: r.question,
      category: r.category,
      duo: [r.duo_opts[0] ?? '', r.duo_opts[1] ?? ''],
      duo_correct: r.duo_correct,
      carre: [r.carre_opts[0] ?? '', r.carre_opts[1] ?? '', r.carre_opts[2] ?? '', r.carre_opts[3] ?? ''],
      carre_correct: r.carre_correct,
      cash: r.cash_answer,
      cash_aliases: r.cash_aliases ?? [],
    })),
  };
}

export function downloadDccJson(data: DccImportFile, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function normalizeQuestion(raw: Record<string, unknown>, index: number): DccImportRow {
  const question = String(raw['question'] ?? '').trim();
  if (!question) throw new Error(`Question ${index + 1} : texte manquant`);

  const category = String(raw['category'] ?? 'Culture générale').trim() || 'Culture générale';

  let duo: string[];
  if (Array.isArray(raw['duo'])) {
    duo = raw['duo'].map((v) => String(v).trim());
  } else if (Array.isArray(raw['duo_opts'])) {
    duo = raw['duo_opts'].map((v) => String(v).trim());
  } else {
    duo = [String(raw['duo_a'] ?? '').trim(), String(raw['duo_b'] ?? '').trim()];
  }
  if (duo.length !== 2 || duo.some((s) => !s)) {
    throw new Error(`Question ${index + 1} : duo doit contenir 2 choix non vides`);
  }

  let carre: string[];
  if (Array.isArray(raw['carre'])) {
    carre = raw['carre'].map((v) => String(v).trim());
  } else if (Array.isArray(raw['carre_opts'])) {
    carre = raw['carre_opts'].map((v) => String(v).trim());
  } else {
    carre = ['carre_a', 'carre_b', 'carre_c', 'carre_d'].map((k) => String(raw[k] ?? '').trim());
  }
  if (carre.length !== 4 || carre.some((s) => !s)) {
    throw new Error(`Question ${index + 1} : carre doit contenir 4 choix non vides`);
  }

  const duoCorrect = Number(raw['duo_correct'] ?? 0);
  const carreCorrect = Number(raw['carre_correct'] ?? 0);
  if (!Number.isInteger(duoCorrect) || duoCorrect < 0 || duoCorrect > 1) {
    throw new Error(`Question ${index + 1} : duo_correct doit être 0 ou 1`);
  }
  if (!Number.isInteger(carreCorrect) || carreCorrect < 0 || carreCorrect > 3) {
    throw new Error(`Question ${index + 1} : carre_correct doit être entre 0 et 3`);
  }

  const cash = String(raw['cash'] ?? raw['cash_answer'] ?? '').trim();
  if (!cash) throw new Error(`Question ${index + 1} : cash / cash_answer manquant`);

  const aliasesRaw = raw['cash_aliases'];
  const cash_aliases = Array.isArray(aliasesRaw)
    ? aliasesRaw.map((v) => String(v).trim()).filter(Boolean)
    : [];

  return {
    question,
    category,
    duo_opts: [duo[0], duo[1]],
    duo_correct: duoCorrect,
    carre_opts: [carre[0], carre[1], carre[2], carre[3]],
    carre_correct: carreCorrect,
    cash_answer: cash,
    cash_aliases,
  };
}

export function parseDccImport(text: string): DccImportRow[] {
  const trimmed = text.trim();
  if (!trimmed) throw new Error('Contenu vide');

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error('JSON invalide — vérifiez virgules et guillemets');
  }

  let items: Record<string, unknown>[];
  if (Array.isArray(parsed)) {
    items = parsed as Record<string, unknown>[];
  } else if (parsed && typeof parsed === 'object' && Array.isArray((parsed as DccImportFile).questions)) {
    items = (parsed as DccImportFile).questions as unknown as Record<string, unknown>[];
  } else {
    throw new Error('Format attendu : { "questions": [...] } ou un tableau JSON');
  }

  if (!items.length) throw new Error('Aucune question trouvée');
  return items.map((item, i) => normalizeQuestion(item, i));
}
