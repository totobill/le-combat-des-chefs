import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { GameService } from '../../core/game.service';
import { Team } from '../../core/models';
import { normalizeScoring, ScoringMap } from '../../core/scoring-config';

export interface DccQuestionRow {
  id: string;
  question: string;
  category: string;
  duo_opts: string[];
  duo_correct: number;
  carre_opts: string[];
  carre_correct: number;
  cash_answer: string;
  cash_aliases: string[];
  used: boolean;
}

export interface MdpWordRow {
  id: string;
  word: string;
  used: boolean;
}

interface DccPendingCash {
  team_id: string;
  team_name: string;
  team_color: string;
  answer: string;
}

interface DccTeamStatus {
  team_id: string;
  team_name: string;
  team_color: string;
  status: string;
  is_active: boolean;
  question_index?: number;
  question_total?: number;
  finished?: boolean;
}

interface DccHostView {
  active?: boolean;
  question_id?: string;
  question?: string;
  category?: string;
  round?: number;
  total?: number;
  episode_total?: number;
  active_team_id?: string;
  active_team_name?: string;
  active_team_color?: string;
  active_team_finished?: boolean;
  can_advance?: boolean;
  team_status?: DccTeamStatus[];
  answers?: { duo: string; carre: string; cash: string };
  pending_cash?: DccPendingCash[];
}

@Component({
  selector: 'app-host',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './host.component.html',
  styleUrl: './host.component.scss',
})
export class HostComponent implements OnInit, OnDestroy {
  teams: Team[] = [];
  scoring: ScoringMap = normalizeScoring({});
  tab = signal<'scores' | 'dcc' | 'mdp' | 'questions' | 'teams'>('scores');
  dccFocusMode = signal(false);

  questions: DccQuestionRow[] = [];
  mdpWords: MdpWordRow[] = [];
  expandedQuestionId: string | null = null;
  showAddQuestion = false;

  dccQuestionId = '';
  dccTeamId = '';
  dccHostView: DccHostView = {};

  mdpTeamId = '';
  mdpPlayerName = '';
  mdpWordId = '';
  mdpHostView: Record<string, unknown> = {};
  mdpError = '';
  mdpWordsFound = 0;
  mdpTimerSec = 30;
  mdpRunning = false;

  newQuestion = {
    question: '',
    category: 'Culture générale',
    duo_a: '',
    duo_b: '',
    duo_correct: 0,
    carre_a: '',
    carre_b: '',
    carre_c: '',
    carre_d: '',
    carre_correct: 0,
    cash_answer: '',
  };

  private pollTimer?: ReturnType<typeof setInterval>;

  constructor(
    public auth: AuthService,
    private game: GameService,
  ) {}

  async ngOnInit(): Promise<void> {
    this.game.connectWs();
    await this.load();
    this.pollTimer = setInterval(() => this.syncFromWs(), 1500);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.game.disconnectWs();
  }

  private syncFromWs(): void {
    const s = this.game.state();
    if (s) {
      this.teams = s.teams;
      this.scoring = normalizeScoring(s.scoring);
    }
    if (this.tab() === 'dcc') {
      void this.refreshDccHost();
    }
    if (this.tab() === 'mdp') {
      void this.refreshMdpHost();
    }
  }

  async load(): Promise<void> {
    const s = await this.game.refresh();
    this.teams = s.teams;
    this.scoring = normalizeScoring(s.scoring);
    if (!this.dccTeamId && this.teams.length) this.dccTeamId = this.teams[0].id;
    await this.loadQuestions();
    await this.loadMdpWords();
    await this.refreshDccHost();
    await this.refreshMdpHost();
    this.bootstrapMdpSelection();
  }

  /** Pré-sélectionne l'équipe uniquement si un seul joueur est connecté quelque part. */
  private bootstrapMdpSelection(): void {
    if (this.mdpTeamId || this.mdpPassageActive()) return;
    const waiting = this.teams.filter((t) => this.mdpPlayersForTeam(t.id).length);
    if (waiting.length === 1) {
      this.selectMdpTeam(waiting[0].id);
    }
  }

  async loadQuestions(): Promise<void> {
    try {
      this.questions = await this.game.apiGet('/dcc/questions');
      if (!this.dccQuestionId && this.questions.length) {
        this.dccQuestionId = this.questions.find((q) => !q.used)?.id ?? this.questions[0].id;
      }
    } catch {
      this.questions = [];
    }
  }

  async loadMdpWords(): Promise<void> {
    try {
      this.mdpWords = await this.game.apiGet('/mdp/words');
      if (!this.mdpWordId && this.mdpWords.length) {
        this.mdpWordId = this.mdpWords.find((w) => !w.used)?.id ?? this.mdpWords[0].id;
      }
    } catch {
      this.mdpWords = [];
    }
  }

  async refreshDccHost(): Promise<void> {
    try {
      this.dccHostView = await this.game.apiGet('/dcc/host-view');
      if (this.dccHostView['question_id']) {
        this.dccQuestionId = this.dccHostView['question_id']!;
      }
      if (this.dccHostView['active_team_id']) {
        this.dccTeamId = this.dccHostView['active_team_id']!;
      }
    } catch {
      this.dccHostView = {};
    }
  }

  async refreshMdpHost(): Promise<void> {
    try {
      this.mdpHostView = await this.game.apiGet('/mdp/host-view');
      const current = this.mdpHostView['current'] as Record<string, unknown> | null;
      this.mdpRunning = !!(
        current && (current['phase'] === 'playing' || current['phase'] === 'countdown')
      );
    } catch {
      this.mdpHostView = {};
      this.mdpRunning = false;
    }
  }

  teamById(id: string): Team | undefined {
    const norm = id.toLowerCase();
    return this.teams.find((t) => t.id === id || t.id.toLowerCase() === norm);
  }

  mdpPassageActive(): boolean {
    return this.mdpRunning;
  }

  mdpActiveTeamName(): string {
    const cur = this.mdpCurrent();
    const tid = cur?.['team_id'] as string | undefined;
    if (tid) return this.teamById(tid)?.name ?? '';
    return this.mdpLobbyTeamName();
  }

  mdpActivePlayerName(): string {
    const cur = this.mdpCurrent();
    return (cur?.['player_name'] as string) || this.mdpLobbyPlayerName();
  }

  mdpJoinBlockedReason(): string {
    if (this.mdpPassageActive()) {
      return 'Terminez le passage en cours avec « Fin du passage » avant de vous connecter à une autre équipe.';
    }
    if (!this.mdpTeamId) return 'Choisissez une équipe.';
    if (!this.mdpPlayerName.trim()) return 'Indiquez le prénom du joueur.';
    if (this.mdpHostView['can_join'] === false) return 'Un passage est déjà en cours.';
    return '';
  }

  dccTeamLabel(status: string): string {
    if (status === 'choosing') return 'Au choix';
    if (status === 'answering') return 'Répond';
    if (status === 'pending') return 'Cash en attente';
    if (status === 'done') return 'Question OK';
    if (status === 'finished') return 'Épreuve terminée';
    return 'En attente';
  }

  dccTeamProgressLabel(ts: DccTeamStatus): string {
    const idx = ts.question_index ?? 0;
    const total = ts.question_total ?? this.dccHostView.episode_total ?? this.questions.length;
    if (ts.finished) return `${total}/${total} questions`;
    return `${idx}/${total} questions`;
  }

  dccTeamsFinishedCount(): number {
    return (this.dccHostView.team_status ?? []).filter((t) => t.finished).length;
  }

  async dccStartEpisode(): Promise<void> {
    if (!this.dccTeamId) {
      alert('Choisissez l\'équipe qui commence');
      return;
    }
    try {
      await this.game.apiPost('/dcc/start-episode', { team_id: this.dccTeamId });
      await this.refreshDccHost();
      this.dccFocusMode.set(true);
      await this.load();
    } catch {
      alert('Impossible de lancer l\'épreuve');
    }
  }

  async dccAssignTeam(teamId?: string): Promise<void> {
    const tid = teamId ?? this.dccTeamId;
    if (!tid) {
      alert('Choisissez une équipe');
      return;
    }
    this.dccTeamId = tid;
    try {
      this.dccHostView = await this.game.apiPost('/dcc/set-team', { team_id: tid });
    } catch {
      alert('Impossible de passer le relais à cette équipe');
    }
  }

  async dccNextTeam(): Promise<void> {
    const next = (this.dccHostView.team_status ?? []).find((t) => !t.finished && !t.is_active);
    if (!next) {
      const unfinished = this.teams.find(
        (t) => !(this.dccHostView.team_status ?? []).find((s) => s.team_id === t.id)?.finished,
      );
      if (!unfinished) {
        alert('Toutes les équipes ont terminé l\'épreuve');
        return;
      }
      await this.dccAssignTeam(unfinished.id);
      return;
    }
    await this.dccAssignTeam(next.team_id);
  }

  activeMdpWord(): MdpWordRow | undefined {
    return this.mdpWords.find((w) => w.id === this.mdpWordId);
  }

  async adjustScore(teamId: string, delta: number, module?: string): Promise<void> {
    await this.game.apiPost('/scores/adjust', {
      team_id: teamId,
      delta,
      ...(module ? { module } : {}),
    });
    await this.load();
  }

  async setScore(team: Team): Promise<void> {
    const score = Math.max(0, Math.round(Number(team.score_total) || 0));
    team.score_total = score;
    await this.game.apiPatch(`/teams/${team.id}`, { score_total: score });
    await this.load();
  }

  async resetAllScores(): Promise<void> {
    if (!confirm('Remettre tous les scores à zéro ?')) return;
    await this.game.apiPost('/reset');
    await this.load();
  }

  async saveTeam(t: Team): Promise<void> {
    await this.game.apiPatch(`/teams/${t.id}`, { name: t.name, color: t.color });
    await this.load();
  }

  async dccNextQuestion(): Promise<void> {
    try {
      this.dccHostView = await this.game.apiPost('/dcc/next-question');
      if (this.dccHostView.question_id) {
        this.dccQuestionId = this.dccHostView.question_id;
      }
      await this.load();
    } catch {
      alert('Passez à l\'équipe suivante ou attendez la fin de la question en cours');
    }
  }

  async dccValidateCash(teamId: string, correct: boolean): Promise<void> {
    await this.game.apiPost('/dcc/validate-cash', { team_id: teamId, correct });
    await this.load();
  }

  dccPendingCash(): DccPendingCash[] {
    return this.dccHostView.pending_cash ?? [];
  }

  hostInFocus(): boolean {
    return this.tab() === 'dcc' && !!this.dccHostView.active && this.dccFocusMode();
  }

  dccQuestionNumber(): number {
    return this.dccHostView.round ?? 0;
  }

  dccQuestionTotal(): number {
    return this.dccHostView.total ?? this.dccHostView.episode_total ?? this.questions.length;
  }

  mdpTeamProgress(teamId: string): { turns_completed?: number; last_player_name?: string } {
    const progress = this.mdpHostView['team_progress'] as Record<
      string,
      { turns_completed?: number; last_player_name?: string }
    > | undefined;
    return progress?.[teamId] ?? {};
  }

  mdpTeamPlayers(): string[] {
    return this.mdpPlayersForTeam(this.mdpTeamId);
  }

  mdpPlayersForTeam(teamId: string): string[] {
    const presence = this.mdpHostView['team_presence'] as Record<string, Record<string, unknown>> | undefined;
    if (!presence || !teamId) return [];
    const direct = presence[teamId];
    const bucket = direct ?? presence[Object.keys(presence).find((k) => k.toLowerCase() === teamId.toLowerCase()) ?? ''];
    if (!bucket) return [];
    return Object.entries(bucket)
      .map(([key, val]) => {
        const name = (val as { name?: string })?.name;
        if (name) return name;
        if (val && typeof val === 'object' && 'at' in val) return key;
        return key;
      })
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b, 'fr'));
  }

  suggestMdpTeamFromPresence(): void {
    if (this.mdpPassageActive() || this.mdpTeamId) return;
    const waiting = this.teams.filter((t) => this.mdpPlayersForTeam(t.id).length);
    if (waiting.length === 1) {
      this.selectMdpTeam(waiting[0].id);
    }
  }

  selectMdpTeam(teamId: string, playerName?: string): void {
    if (this.mdpPassageActive()) {
      this.mdpError =
        'Passage en cours sur ' +
        this.mdpActiveTeamName() +
        ' — cliquez « Fin du passage » pour enchaîner sur une autre équipe.';
      return;
    }
    this.mdpError = '';
    this.mdpTeamId = teamId;
    const players = this.mdpPlayersForTeam(teamId);
    if (playerName && players.includes(playerName)) {
      this.mdpPlayerName = playerName;
    } else {
      this.onMdpTeamChange();
    }
  }

  mdpLobbyPlayerName(): string {
    const lobby = this.mdpHostView['lobby'] as { player_name?: string } | undefined;
    return lobby?.player_name ?? this.mdpPlayerName;
  }

  async mdpLeaveTeam(): Promise<void> {
    this.mdpError = '';
    try {
      await this.game.apiPost('/mdp/host-leave');
      await this.refreshMdpHost();
    } catch {
      this.mdpError = 'Impossible de se déconnecter.';
    }
  }

  onMdpTeamChange(): void {
    const players = this.mdpTeamPlayers();
    if (players.length && !players.includes(this.mdpPlayerName)) {
      this.mdpPlayerName = players[0];
    }
  }

  exitDccFocus(): void {
    this.dccFocusMode.set(false);
  }

  enterDccFocus(): void {
    this.dccFocusMode.set(true);
  }

  private stopMdpTimer(): void {
    this.mdpRunning = false;
  }

  mdpCanJoin(): boolean {
    return !this.mdpJoinBlockedReason();
  }

  mdpCanEnd(): boolean {
    return !!this.mdpHostView['can_end'];
  }

  mdpPointsPerWord(): number {
    return (this.mdpHostView['points_per_word'] as number) ?? this.scoring.mdp.points_per_word;
  }

  mdpCurrent(): Record<string, unknown> | null {
    return (this.mdpHostView['current'] as Record<string, unknown>) || null;
  }

  mdpCountdownSec(): number {
    const cur = this.mdpCurrent();
    return (cur?.['countdown_sec'] as number) ?? 0;
  }

  mdpTurnRemaining(): number {
    const cur = this.mdpCurrent();
    return (cur?.['remaining_sec'] as number) ?? 0;
  }

  mdpLobbyTeamName(): string {
    const lobby = this.mdpHostView['lobby'] as { team_id?: string } | undefined;
    if (!lobby?.team_id) return '';
    return this.teamById(lobby.team_id)?.name ?? '';
  }

  async mdpJoinTeam(): Promise<void> {
    this.mdpError = '';
    try {
      await this.game.apiPost('/mdp/host-join', {
        team_id: this.mdpTeamId,
        player_name: this.mdpPlayerName.trim(),
      });
      this.mdpRunning = false;
      await this.refreshMdpHost();
      await this.load();
    } catch {
      this.mdpError = 'Impossible de se connecter — un passage est peut-être en cours.';
    }
  }

  async mdpValidateWord(): Promise<void> {
    this.mdpError = '';
    try {
      this.mdpHostView = await this.game.apiPost('/mdp/validate');
      await this.load();
    } catch {
      this.mdpError = 'Validation impossible.';
    }
  }

  async mdpCancelWord(): Promise<void> {
    this.mdpError = '';
    try {
      this.mdpHostView = await this.game.apiPost('/mdp/cancel-word');
    } catch {
      this.mdpError = 'Impossible de changer le mot.';
    }
  }

  mdpCanStart(): boolean {
    return this.mdpHostView['can_join'] !== false;
  }

  async mdpStartTurn(): Promise<void> {
    await this.mdpJoinTeam();
  }

  async mdpEndTurn(): Promise<void> {
    await this.game.apiPost('/mdp/end-turn/force');
    this.stopMdpTimer();
    this.mdpError = '';
    await this.refreshMdpHost();
    await this.load();
    this.suggestMdpTeamFromPresence();
  }

  mdpPickRandomWord(): void {
    const pool = this.mdpWords.filter((w) => !w.used);
    const pick = pool.length ? pool[Math.floor(Math.random() * pool.length)] : this.mdpWords[0];
    if (pick) this.mdpWordId = pick.id;
  }

  toggleQuestion(id: string): void {
    this.expandedQuestionId = this.expandedQuestionId === id ? null : id;
  }

  async addQuestion(): Promise<void> {
    const n = this.newQuestion;
    await this.game.apiPost('/dcc/questions', {
      question: n.question.trim(),
      category: n.category.trim() || 'Culture générale',
      duo_opts: [n.duo_a.trim(), n.duo_b.trim()],
      duo_correct: n.duo_correct,
      carre_opts: [n.carre_a, n.carre_b, n.carre_c, n.carre_d].map((s) => s.trim()),
      carre_correct: n.carre_correct,
      cash_answer: n.cash_answer.trim(),
      cash_aliases: [],
    });
    this.showAddQuestion = false;
    this.newQuestion = {
      question: '',
      category: 'Culture générale',
      duo_a: '',
      duo_b: '',
      duo_correct: 0,
      carre_a: '',
      carre_b: '',
      carre_c: '',
      carre_d: '',
      carre_correct: 0,
      cash_answer: '',
    };
    await this.loadQuestions();
  }
}
