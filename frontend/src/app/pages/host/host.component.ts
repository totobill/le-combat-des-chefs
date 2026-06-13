import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { BoardDisplayPayload, DccLevel } from '../../core/board-display';
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

  questions: DccQuestionRow[] = [];
  mdpWords: MdpWordRow[] = [];
  expandedQuestionId: string | null = null;
  showAddQuestion = false;

  dccQuestionId = '';
  dccTeamLevels: Record<string, DccLevel> = {};
  dccBoard: BoardDisplayPayload | null = null;

  mdpTeamId = '';
  mdpPlayerIndex = 1;
  mdpWordId = '';
  mdpWordsFound = 0;
  mdpTimerSec = 30;
  mdpRunning = false;
  private mdpTimer?: ReturnType<typeof setInterval>;

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
    this.stopMdpTimer();
    this.game.disconnectWs();
  }

  private syncFromWs(): void {
    const s = this.game.state();
    if (s) {
      this.teams = s.teams;
      this.scoring = normalizeScoring(s.scoring);
    }
  }

  async load(): Promise<void> {
    const s = await this.game.refresh();
    this.teams = s.teams;
    this.scoring = normalizeScoring(s.scoring);
    if (!this.mdpTeamId && this.teams.length) this.mdpTeamId = this.teams[0].id;
    for (const t of this.teams) {
      if (!this.dccTeamLevels[t.id]) this.dccTeamLevels[t.id] = 'duo';
    }
    await this.loadQuestions();
    await this.loadMdpWords();
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

  activeDccQuestion(): DccQuestionRow | undefined {
    return this.questions.find((q) => q.id === this.dccQuestionId);
  }

  activeMdpWord(): MdpWordRow | undefined {
    return this.mdpWords.find((w) => w.id === this.mdpWordId);
  }

  dccAnswerForLevel(q: DccQuestionRow, level: DccLevel): string {
    if (level === 'duo') return q.duo_opts[q.duo_correct];
    if (level === 'carre') return q.carre_opts[q.carre_correct];
    return q.cash_answer;
  }

  async pushBoard(payload: BoardDisplayPayload): Promise<void> {
    this.dccBoard = payload;
    await this.game.apiPost('/board/display', payload);
  }

  async clearBoard(): Promise<void> {
    this.dccBoard = null;
    await this.game.apiDelete('/board/display');
  }

  async adjustScore(teamId: string, delta: number): Promise<void> {
    await this.game.apiPost('/scores/adjust', { team_id: teamId, delta });
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

  async dccShowQuestion(): Promise<void> {
    const q = this.activeDccQuestion();
    if (!q) return;
    await this.pushBoard({
      mode: 'dcc',
      title: 'Duo · Carré · Cash',
      subtitle: q.category,
      question: q.question,
      category: q.category,
      show_options: false,
      show_answer: false,
    });
  }

  async dccShowChoices(team: Team): Promise<void> {
    const q = this.activeDccQuestion();
    if (!q) return;
    const level = this.dccTeamLevels[team.id] ?? 'duo';
    const options = level === 'duo' ? q.duo_opts : level === 'carre' ? q.carre_opts : [];
    await this.pushBoard({
      mode: 'dcc',
      title: 'Duo · Carré · Cash',
      subtitle: q.category,
      question: q.question,
      category: q.category,
      level,
      options,
      show_options: level !== 'cash',
      show_answer: false,
      team_name: team.name,
      team_color: team.color,
    });
  }

  async dccRevealAnswer(): Promise<void> {
    const q = this.activeDccQuestion();
    if (!q || !this.dccBoard) return;
    const level = this.dccBoard.level ?? 'duo';
    await this.pushBoard({
      ...this.dccBoard,
      show_answer: true,
      answer: this.dccAnswerForLevel(q, level),
    });
  }

  async dccValidate(team: Team, correct: boolean): Promise<void> {
    const q = this.activeDccQuestion();
    if (!q) return;
    const level = this.dccTeamLevels[team.id] ?? 'duo';
    const pts = correct ? this.scoring.dcc[level] : 0;
    if (pts > 0) {
      await this.game.apiPost('/scores/adjust', { team_id: team.id, delta: pts });
    }
    await this.pushBoard({
      mode: 'dcc',
      title: 'Duo · Carré · Cash',
      subtitle: q.category,
      question: q.question,
      level,
      show_answer: true,
      answer: this.dccAnswerForLevel(q, level),
      team_name: team.name,
      team_color: team.color,
      feedback: correct ? `${team.name} — Bonne réponse (+${pts} pts)` : `${team.name} — Mauvaise réponse`,
    });
    await this.load();
  }

  private stopMdpTimer(): void {
    if (this.mdpTimer) {
      clearInterval(this.mdpTimer);
      this.mdpTimer = undefined;
    }
    this.mdpRunning = false;
  }

  async mdpStartTurn(): Promise<void> {
    const word = this.activeMdpWord();
    const team = this.teams.find((t) => t.id === this.mdpTeamId);
    if (!word || !team) return;

    this.stopMdpTimer();
    this.mdpWordsFound = 0;
    this.mdpTimerSec = 30;
    this.mdpRunning = true;

    await this.pushBoard({
      mode: 'mdp',
      title: 'Mot de Passe',
      team_name: team.name,
      team_color: team.color,
      player_label: `Joueur ${this.mdpPlayerIndex}`,
      word: word.word,
      words_found: 0,
      timer_sec: 30,
      timer_running: true,
    });

    this.mdpTimer = setInterval(async () => {
      this.mdpTimerSec -= 1;
      await this.pushBoard({
        mode: 'mdp',
        title: 'Mot de Passe',
        team_name: team.name,
        team_color: team.color,
        player_label: `Joueur ${this.mdpPlayerIndex}`,
        word: word.word,
        words_found: this.mdpWordsFound,
        timer_sec: this.mdpTimerSec,
        timer_running: this.mdpTimerSec > 0,
      });
      if (this.mdpTimerSec <= 0) this.stopMdpTimer();
    }, 1000);
  }

  async mdpWordFound(): Promise<void> {
    const team = this.teams.find((t) => t.id === this.mdpTeamId);
    const word = this.activeMdpWord();
    if (!team || !word) return;

    this.mdpWordsFound += 1;
    const pts = this.scoring.mdp.points_per_word;
    await this.game.apiPost('/scores/adjust', { team_id: team.id, delta: pts });

    await this.pushBoard({
      mode: 'mdp',
      title: 'Mot de Passe',
      team_name: team.name,
      team_color: team.color,
      player_label: `Joueur ${this.mdpPlayerIndex}`,
      word: word.word,
      words_found: this.mdpWordsFound,
      timer_sec: this.mdpTimerSec,
      timer_running: this.mdpRunning,
      feedback: `Mot trouvé ! +${pts} pt`,
    });
    await this.load();
  }

  async mdpEndTurn(): Promise<void> {
    this.stopMdpTimer();
    const team = this.teams.find((t) => t.id === this.mdpTeamId);
    await this.pushBoard({
      mode: 'mdp',
      title: 'Mot de Passe',
      team_name: team?.name ?? '',
      team_color: team?.color ?? '',
      player_label: `Joueur ${this.mdpPlayerIndex}`,
      word: '',
      words_found: this.mdpWordsFound,
      timer_sec: 0,
      timer_running: false,
      feedback: `Fin du passage — ${this.mdpWordsFound} mot(s)`,
    });
  }

  mdpPickRandomWord(): void {
    const pool = this.mdpWords.filter((w) => !w.used);
    const pick = pool.length ? pool[Math.floor(Math.random() * pool.length)] : this.mdpWords[0];
    if (pick) this.mdpWordId = pick.id;
  }

  toggleQuestion(id: string): void {
    this.expandedQuestionId = this.expandedQuestionId === id ? null : id;
  }

  async showOnBoard(q: DccQuestionRow): Promise<void> {
    this.dccQuestionId = q.id;
    await this.dccShowQuestion();
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
