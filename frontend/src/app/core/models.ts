export interface Team {
  id: string;
  name: string;
  color: string;
  member_count: number;
  score_total: number;
  rank: number | null;
  eliminated: boolean;
}

export interface GameState {
  session: { id: string; code: string; status: string; current_module: string | null };
  teams: Team[];
  scoring: Record<string, Record<string, unknown>>;
  event: { module: string | null; state: Record<string, unknown> };
  program: ProgramItem[];
}

export interface ProgramItem {
  id: string;
  label: string;
  phase: string;
  icon: string;
  status: string;
}
