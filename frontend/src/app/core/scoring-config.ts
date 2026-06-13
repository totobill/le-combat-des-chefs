export interface PlacementPoints {
  '1': number;
  '2': number;
  '3': number;
}

export interface ScoringMap {
  mdp: { points_per_word: number; placement: PlacementPoints };
  dcc: { duo: number; carre: number; cash: number; placement: PlacementPoints };
  chips: {
    points_per_correct: number;
    placement: PlacementPoints;
    malus_per_wrong: number;
  };
  molkky: { placement: PlacementPoints };
  paroles: { points_per_word: number };
  piscine: { placement: PlacementPoints };
  poignards: { handicap_seconds: PlacementPoints };
}

export type ScoringModuleId = keyof ScoringMap;

export const SCORING_MODULES: {
  id: ScoringModuleId;
  label: string;
  icon: string;
  hint: string;
}[] = [
  {
    id: 'mdp',
    label: 'Mot de Passe',
    icon: '🎭',
    hint: 'Points par mot trouvé pendant les passages + bonus de classement final.',
  },
  {
    id: 'dcc',
    label: 'Duo / Carré / Cash',
    icon: '🎯',
    hint: 'Points par bonne réponse selon le niveau + bonus 1er/2e/3e de l\'épreuve.',
  },
  {
    id: 'chips',
    label: 'Chips',
    icon: '🥔',
    hint: 'Points par saveur trouvée, malus par erreur + bonus de classement final.',
  },
  {
    id: 'molkky',
    label: 'Mölkky',
    icon: '🎳',
    hint: 'Points selon le classement de l\'épreuve.',
  },
  {
    id: 'paroles',
    label: 'N\'oubliez pas les paroles',
    icon: '🎵',
    hint: 'Points par mot correctement retrouvé.',
  },
  {
    id: 'piscine',
    label: 'Piscine — Relais',
    icon: '🏊',
    hint: 'Points selon le classement du relais.',
  },
  {
    id: 'poignards',
    label: 'Épreuve des poignards',
    icon: '🔪',
    hint: 'Handicap en secondes ajouté au chrono selon le classement actuel.',
  },
];

export const RESULT_MODULES: { id: string; label: string; icon: string }[] = [
  { id: 'mdp', label: 'Mot de Passe', icon: '🎭' },
  { id: 'dcc', label: 'Duo / Carré / Cash', icon: '🎯' },
  { id: 'chips', label: 'Chips', icon: '🥔' },
  { id: 'molkky', label: 'Mölkky', icon: '🎳' },
  { id: 'paroles', label: 'Paroles', icon: '🎵' },
  { id: 'piscine', label: 'Piscine', icon: '🏊' },
  { id: 'poignards', label: 'Poignards', icon: '🔪' },
];

export const DEFAULT_SCORING: ScoringMap = {
  mdp: { points_per_word: 2, placement: { '1': 20, '2': 12, '3': 6 } },
  dcc: { duo: 1, carre: 3, cash: 6, placement: { '1': 10, '2': 6, '3': 3 } },
  chips: {
    points_per_correct: 1,
    placement: { '1': 15, '2': 10, '3': 5 },
    malus_per_wrong: 1,
  },
  molkky: { placement: { '1': 25, '2': 15, '3': 8 } },
  paroles: { points_per_word: 1 },
  piscine: { placement: { '1': 20, '2': 12, '3': 6 } },
  poignards: { handicap_seconds: { '1': 0, '2': 15, '3': 30 } },
};

function num(value: unknown, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function placement(raw: unknown, defaults: PlacementPoints): PlacementPoints {
  const p = (raw ?? {}) as Record<string, unknown>;
  return {
    '1': num(p['1'], defaults['1']),
    '2': num(p['2'], defaults['2']),
    '3': num(p['3'], defaults['3']),
  };
}

export function normalizeScoring(raw: Record<string, Record<string, unknown>>): ScoringMap {
  const mdp = raw['mdp'];
  const dcc = raw['dcc'];
  const chips = raw['chips'];
  const molkky = raw['molkky'];
  const paroles = raw['paroles'];
  const piscine = raw['piscine'];
  const poignards = raw['poignards'];

  return {
    mdp: {
      points_per_word: num(mdp?.['points_per_word'], DEFAULT_SCORING.mdp.points_per_word),
      placement: placement(mdp?.['placement'], DEFAULT_SCORING.mdp.placement),
    },
    dcc: {
      duo: num(dcc?.['duo'], DEFAULT_SCORING.dcc.duo),
      carre: num(dcc?.['carre'], DEFAULT_SCORING.dcc.carre),
      cash: num(dcc?.['cash'], DEFAULT_SCORING.dcc.cash),
      placement: placement(dcc?.['placement'], DEFAULT_SCORING.dcc.placement),
    },
    chips: {
      points_per_correct: num(
        chips?.['points_per_correct'],
        DEFAULT_SCORING.chips.points_per_correct,
      ),
      placement: placement(chips?.['placement'], DEFAULT_SCORING.chips.placement),
      malus_per_wrong: num(chips?.['malus_per_wrong'], DEFAULT_SCORING.chips.malus_per_wrong),
    },
    molkky: { placement: placement(molkky?.['placement'], DEFAULT_SCORING.molkky.placement) },
    paroles: {
      points_per_word: num(paroles?.['points_per_word'], DEFAULT_SCORING.paroles.points_per_word),
    },
    piscine: { placement: placement(piscine?.['placement'], DEFAULT_SCORING.piscine.placement) },
    poignards: {
      handicap_seconds: placement(
        poignards?.['handicap_seconds'],
        DEFAULT_SCORING.poignards.handicap_seconds,
      ),
    },
  };
}
