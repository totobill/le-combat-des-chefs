export type BoardMode = 'scores' | 'simple' | 'dcc' | 'mdp';
export type DccLevel = 'duo' | 'carre' | 'cash';

export interface BoardDisplayPayload {
  mode: BoardMode;
  title?: string;
  subtitle?: string;
  question?: string;
  category?: string;
  level?: DccLevel;
  options?: string[];
  show_options?: boolean;
  show_answer?: boolean;
  answer?: string;
  team_name?: string;
  team_color?: string;
  player_label?: string;
  word?: string;
  words_found?: number;
  timer_sec?: number;
  timer_running?: boolean;
  feedback?: string;
}

export function isGameOnBoard(board: BoardDisplayPayload | null | undefined): boolean {
  if (!board) return false;
  return board.mode === 'dcc' || board.mode === 'mdp' || (board.mode === 'simple' && !!board.question);
}
