import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { BoardDisplayPayload } from '../../core/board-display';
import { GameService } from '../../core/game.service';
import { GameState, Team } from '../../core/models';
import { RESULT_MODULES } from '../../core/scoring-config';

type GameStatus = 'waiting' | 'live' | 'done';

@Component({
  selector: 'app-team',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './team.component.html',
  styleUrl: './team.component.scss',
})
export class TeamComponent implements OnInit, OnDestroy {
  teams: Team[] = [];
  myTeam: Team | null = null;
  currentModule: string | null = null;
  eventState: Record<string, unknown> = {};
  board: BoardDisplayPayload | null = null;
  modulePoints: Record<string, Record<string, number>> = {};

  games = RESULT_MODULES;
  expandedGame = signal<string | null>(null);
  showScores = signal(true);

  // DCC (backend module)
  dccView: Record<string, unknown> = {};
  dccError = '';
  dccAnswer: string | number = '';
  cashInput = '';

  // MDP (backend module)
  mdpView: Record<string, unknown> = {};
  mdpCountdown = signal(0);

  // Paroles / Chips
  parolesView: Record<string, unknown> = {};
  parolesAnswers: string[] = [];
  chipsView: Record<string, unknown> = {};
  chipsGuesses = '';

  private modulePoll?: ReturnType<typeof setInterval>;
  private mdpPoll?: ReturnType<typeof setInterval>;
  private mdpPresenceTimer?: ReturnType<typeof setInterval>;

  constructor(
    public auth: AuthService,
    private game: GameService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.game.connectWs();
    void this.game.refresh().then((s) => this.applyState(s));
    void this.registerMdpPresence();
    this.mdpPresenceTimer = setInterval(() => void this.registerMdpPresence(), 10000);
    this.modulePoll = setInterval(() => void this.refreshModuleViews(), 1500);
    this.mdpPoll = setInterval(() => void this.pollMdp(), 500);
  }

  ngOnDestroy(): void {
    if (this.modulePoll) clearInterval(this.modulePoll);
    if (this.mdpPoll) clearInterval(this.mdpPoll);
    if (this.mdpPresenceTimer) clearInterval(this.mdpPresenceTimer);
  }

  /** Signal à l'animateur que ce joueur est sur son équipe (dès l'écran équipe). */
  private async registerMdpPresence(): Promise<void> {
    try {
      await this.game.apiPost('/mdp/present');
    } catch {
      /* */
    }
  }

  private applyState(s: GameState): void {
    const tid = this.auth.teamId();
    this.teams = [...s.teams].sort((a, b) => b.score_total - a.score_total);
    this.myTeam = s.teams.find((t) => t.id === tid) ?? null;
    this.currentModule = s.event.module;
    this.eventState = s.event.state;
    this.board = (s.event.state['board'] as BoardDisplayPayload) || null;
    this.modulePoints = (s.event.state['module_points'] as Record<string, Record<string, number>>) || {};
  }

  async refreshModuleViews(): Promise<void> {
    const s = this.game.state();
    if (s) this.applyState(s);
    else await this.game.refresh().then((st) => this.applyState(st));

    const mod = this.currentModule;
    const open = this.expandedGame();

    if (mod === 'dcc' || open === 'dcc' || this.board?.mode === 'dcc') {
      try {
        this.dccView = await this.game.apiGet('/dcc/current');
      } catch {
        /* */
      }
    }
    if (mod === 'mdp' || open === 'mdp') {
      await this.pollMdp();
    }
    if (mod === 'paroles' || open === 'paroles') {
      try {
        this.parolesView = await this.game.apiGet('/paroles/view');
        const n = (this.parolesView['blank_count'] as number) || 0;
        if (this.parolesAnswers.length !== n) {
          this.parolesAnswers = Array(n).fill('');
        }
      } catch {
        /* */
      }
    }
    if (mod === 'chips' || open === 'chips') {
      try {
        this.chipsView = await this.game.apiGet('/chips/view');
      } catch {
        /* */
      }
    }
  }

  async pollMdp(): Promise<void> {
    if (this.currentModule !== 'mdp' && this.expandedGame() !== 'mdp') return;
    try {
      this.mdpView = await this.game.apiGet('/mdp/player-view');
      this.mdpCountdown.set((this.mdpView['countdown_sec'] as number) ?? 0);
    } catch {
      /* */
    }
  }

  mdpPlayerLabel(): string {
    const fromView = this.mdpView['player_name'] as string | undefined;
    if (fromView) return fromView;
    return this.auth.auth()?.displayName ?? 'Joueur';
  }

  toggleGame(id: string): void {
    this.expandedGame.set(id);
    void this.refreshModuleViews();
  }

  closeGame(): void {
    this.expandedGame.set(null);
  }

  switchPlayer(): void {
    this.auth.logout(false);
    void this.router.navigate(['/join']);
  }

  gameLabel(id: string): string {
    return this.games.find((g) => g.id === id)?.label ?? id;
  }

  gameIcon(id: string): string {
    return this.games.find((g) => g.id === id)?.icon ?? '🎮';
  }

  myPoints(moduleId: string): number {
    const tid = this.auth.teamId();
    if (!tid) return 0;
    return this.modulePoints[moduleId]?.[tid] ?? 0;
  }

  gameStatus(moduleId: string): GameStatus {
    if (this.myPoints(moduleId) > 0 || this.hasModuleResult(moduleId)) return 'done';
    if (this.isGameLive(moduleId)) return 'live';
    return 'waiting';
  }

  statusLabel(moduleId: string): string {
    const st = this.gameStatus(moduleId);
    if (st === 'done') return `${this.myPoints(moduleId)} pt`;
    if (st === 'live') return 'En cours';
    return '—';
  }

  private hasModuleResult(moduleId: string): boolean {
    const tid = this.auth.teamId();
    if (!tid) return false;
    const mod = this.eventState[moduleId] as Record<string, unknown> | undefined;
    if (!mod) return false;
    if (moduleId === 'dcc') {
      const results = mod['results'] as Record<string, unknown> | undefined;
      return !!results?.[tid];
    }
    if (moduleId === 'mdp') {
      const scores = mod['team_scores'] as Record<string, unknown[]> | undefined;
      return !!(scores?.[tid]?.length);
    }
    if (moduleId === 'paroles' || moduleId === 'chips') {
      const results = mod['results'] as Record<string, unknown> | undefined;
      return !!results?.[tid];
    }
    return !!mod['done'] || !!mod['finalized'];
  }

  isGameLive(moduleId: string): boolean {
    if (moduleId === 'mdp') {
      const ph = this.mdpPhase();
      return ph === 'lobby' || ph === 'countdown' || ph === 'playing';
    }
    if (this.currentModule === moduleId) return true;
    const b = this.board;
    if (!b) return false;
    if (moduleId === 'dcc' && b.mode === 'dcc') return true;
    return false;
  }

  boardForGame(moduleId: string): BoardDisplayPayload | null {
    const b = this.board;
    if (!b) return null;
    if (moduleId === 'dcc' && b.mode === 'dcc') return b;
    return null;
  }

  isBoardForMe(board: BoardDisplayPayload): boolean {
    if (!board.team_name) return true;
    return board.team_name === this.myTeam?.name;
  }

  boardLevelLabel(level?: string): string {
    if (level === 'duo') return 'Duo';
    if (level === 'carre') return 'Carré';
    if (level === 'cash') return 'Cash';
    return '';
  }

  dccActive(): boolean {
    return !!this.dccView['active'];
  }

  dccShowPanel(): boolean {
    const st = this.dccStatus();
    if (st !== 'idle') return true;
    return this.currentModule === 'dcc' || this.board?.mode === 'dcc';
  }

  dccWaitingMessage(): string {
    return (this.dccView['message'] as string) || 'En attente de votre tour…';
  }

  dccProgressLabel(): string {
    const round = this.dccView['round'] as number | undefined;
    const total = this.dccView['total'] as number | undefined;
    if (round && total) return `Question ${round} / ${total}`;
    return '';
  }

  dccStatus(): string {
    if (this.dccView['active'] && !this.dccView['status']) return 'choosing';
    return (this.dccView['status'] as string) || 'idle';
  }

  dccQuestionText(): string {
    return (this.dccView['question'] as string) || this.boardForGame('dcc')?.question || '';
  }

  dccCategory(): string {
    return (this.dccView['category'] as string) || this.boardForGame('dcc')?.category || '';
  }

  dccTeamResult(): {
    correct?: boolean;
    points?: number;
    mode?: string;
    correct_answer?: { duo: string; carre: string; cash: string };
  } | null {
    const fromView = this.dccView['result'] as {
      correct?: boolean;
      points?: number;
      mode?: string;
      correct_answer?: { duo: string; carre: string; cash: string };
    } | undefined;
    return fromView ?? this.dccResult();
  }

  dccCorrectLabel(result: { mode?: string; correct_answer?: { duo: string; carre: string; cash: string } }): string {
    if (!result.correct_answer || !result.mode) return '';
    if (result.mode === 'duo') return result.correct_answer.duo;
    if (result.mode === 'carre') return result.correct_answer.carre;
    return result.correct_answer.cash;
  }

  dccResult(): { correct?: boolean; points?: number; mode?: string; correct_answer?: { duo: string; carre: string; cash: string } } | null {
    const tid = this.auth.teamId();
    if (!tid) return null;
    const dcc = this.eventState['dcc'] as Record<string, unknown> | undefined;
    const results = dcc?.['results'] as Record<string, unknown> | undefined;
    const teamResults = results?.[tid];
    const qid = (this.dccView['question_id'] as string) || (this.eventState['dcc'] as { question_id?: string })?.question_id;
    if (teamResults && qid && typeof teamResults === 'object' && qid in (teamResults as object)) {
      return (teamResults as Record<string, { correct: boolean; points: number; mode: string; correct_answer?: { duo: string; carre: string; cash: string } }>)[qid];
    }
    if (teamResults && typeof teamResults === 'object' && 'correct' in (teamResults as object)) {
      return teamResults as { correct: boolean; points: number; mode: string; correct_answer?: { duo: string; carre: string; cash: string } };
    }
    return null;
  }

  mdpPhase(): string {
    return (this.mdpView['phase'] as string) || 'waiting';
  }

  mdpHostReady(): boolean {
    return !!this.mdpView['host_ready'];
  }

  mdpTurnPoints(): number {
    return (this.mdpView['turn_points'] as number) ?? 0;
  }

  mdpWordsFound(): number {
    return (this.mdpView['words_found'] as number) ?? 0;
  }

  mdpTurnRemaining(): number {
    return (this.mdpView['remaining_sec'] as number) ?? 0;
  }

  mdpPointsPerWord(): number {
    return (this.mdpView['points_per_word'] as number) ?? 2;
  }

  async mdpStartCountdown(): Promise<void> {
    await this.game.apiPost('/mdp/start-countdown');
    await this.pollMdp();
  }

  async mdpPassWord(): Promise<void> {
    await this.game.apiPost('/mdp/pass');
    await this.pollMdp();
  }

  async mdpNextWord(): Promise<void> {
    await this.mdpPassWord();
  }

  dccOpts(): string[] {
    return (this.dccView['options'] as string[]) || [];
  }

  isDccRevealed(): boolean {
    const dcc = this.eventState['dcc'] as { revealed?: boolean } | undefined;
    return !!dcc?.revealed;
  }

  parolesLocked(): boolean {
    const tid = this.auth.teamId();
    const locked = this.parolesView['locked'] as Record<string, boolean> | undefined;
    return !!tid && !!locked?.[tid];
  }

  parolesResult(): { score?: number } | null {
    const tid = this.auth.teamId();
    if (!tid) return null;
    const mod = this.eventState['paroles'] as Record<string, unknown> | undefined;
    const results = mod?.['results'] as Record<string, { score: number }> | undefined;
    return results?.[tid] ?? null;
  }

  chipsResult(): { points?: number } | null {
    const tid = this.auth.teamId();
    if (!tid) return null;
    const mod = this.eventState['chips'] as Record<string, unknown> | undefined;
    const results = mod?.['results'] as Record<string, { points: number }> | undefined;
    return results?.[tid] ?? null;
  }

  chipsSubmitted(): boolean {
    const tid = this.auth.teamId();
    if (!tid) return false;
    const mod = this.eventState['chips'] as Record<string, unknown> | undefined;
    const guesses = mod?.['team_guesses'] as Record<string, unknown> | undefined;
    return !!guesses?.[tid];
  }

  dccAnswered(): boolean {
    const tid = this.auth.teamId();
    if (!tid) return false;
    const dcc = this.eventState['dcc'] as Record<string, unknown> | undefined;
    const answers = dcc?.['team_answers'] as Record<string, unknown> | undefined;
    return tid in (answers || {});
  }

  async dccPickOption(index: number): Promise<void> {
    this.dccAnswer = index;
    await this.dccSubmitAnswer();
  }

  async dccChoose(mode: string): Promise<void> {
    this.dccError = '';
    this.dccAnswer = '';
    this.cashInput = '';
    try {
      this.dccView = await this.game.apiPost<Record<string, unknown>>('/dcc/choose', { mode });
    } catch {
      this.dccError = 'Impossible de choisir ce mode. Réessayez ou demandez à l’animateur de relancer la question.';
      await this.refreshModuleViews();
    }
  }

  async dccSubmitAnswer(): Promise<void> {
    this.dccError = '';
    const mode = this.dccView['mode'] as string;
    let answer: string | number = this.cashInput;
    if (mode === 'duo' || mode === 'carre') answer = this.dccAnswer;
    try {
      this.dccView = await this.game.apiPost<Record<string, unknown>>('/dcc/answer', { answer });
      this.dccAnswer = '';
      this.cashInput = '';
    } catch {
      this.dccError = 'Envoi impossible. Vérifiez votre réponse et réessayez.';
      await this.refreshModuleViews();
    }
  }

  async parolesSubmit(): Promise<void> {
    await this.game.apiPost('/paroles/submit', { answers: this.parolesAnswers });
    await this.refreshModuleViews();
  }

  async chipsSubmit(): Promise<void> {
    const guesses = this.chipsGuesses.split(',').map((g) => g.trim()).filter(Boolean);
    await this.game.apiPost('/chips/guess', { guesses });
    await this.refreshModuleViews();
  }
}
