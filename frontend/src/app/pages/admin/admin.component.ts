import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { KeyValuePipe, NgTemplateOutlet } from '@angular/common';
import QRCode from 'qrcode';
import { AuthService } from '../../core/auth.service';
import { GameService } from '../../core/game.service';
import { Team } from '../../core/models';
import {
  normalizeScoring,
  RESULT_MODULES,
  SCORING_MODULES,
  ScoringMap,
  ScoringModuleId,
} from '../../core/scoring-config';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [FormsModule, RouterLink, KeyValuePipe, NgTemplateOutlet],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.scss',
})
export class AdminComponent implements OnInit, OnDestroy {
  teams: Team[] = [];
  scoring: ScoringMap = normalizeScoring({});
  eventState: Record<string, unknown> = {};
  currentModule: string | null = null;

  scoringModule = signal<ScoringModuleId>('mdp');
  resultModule = signal('mdp');
  scoringModules = SCORING_MODULES;
  resultModules = RESULT_MODULES;
  savingScoring = signal(false);
  scoringSaved = signal(false);
  tab = signal<'teams' | 'scoring' | 'content' | 'results' | 'links'>('teams');
  contentTab = signal<'mdp' | 'dcc'>('mdp');

  // Contenu jeux
  mdpWords: { id: string; word: string; used: boolean }[] = [];
  dccQuestions: {
    id: string;
    question: string;
    category: string;
    duo_opts: string[];
    duo_correct: number;
    carre_opts: string[];
    carre_correct: number;
    cash_answer: string;
    used: boolean;
  }[] = [];
  newMdpWord = '';
  newMdpBulk = '';
  newDccQuestion = {
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
  contentSaved = signal(false);

  publicUrl = environment.publicUrl;
  sessionCode = environment.sessionCode;
  linkQrCodes: { label: string; path: string; url: string; dataUrl: string }[] = [];
  teamJoinQrs: { teamId: string; name: string; color: string; url: string; dataUrl: string }[] = [];

  // Résultats — saisie
  placement: Record<string, number> = {};
  dccPlacement: Record<string, number> = {};
  chipsPlacement: Record<string, number> = {};
  mdpTeamId = '';
  mdpPlayerIndex = 0;
  mdpHostView: Record<string, unknown> = {};
  mdpError = '';
  chips: { id: string; name: string; flavors: string[] }[] = [];
  selectedChipId = '';
  flavorsToGuess = '';
  chipsInputs: Record<string, { correct: string; wrong: number }> = {};

  private pollTimer?: ReturnType<typeof setInterval>;

  constructor(
    public auth: AuthService,
    private game: GameService,
  ) {}

  async ngOnInit(): Promise<void> {
    this.game.connectWs();
    await this.load();
    await this.loadContent();
    try {
      this.chips = await this.game.apiGet('/chips');
      if (this.chips.length) this.selectedChipId = this.chips[0].id;
    } catch {
      /* */
    }
    this.pollTimer = setInterval(() => this.syncFromWs(), 1500);
    await this.buildLinkQrCodes();
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.game.disconnectWs();
  }

  private syncFromWs(): void {
    const s = this.game.state();
    if (!s) return;
    this.teams = s.teams;
    this.eventState = s.event.state;
    this.currentModule = s.event.module;
    if (this.resultModule() === 'mdp') {
      this.refreshMdpHost();
    }
  }

  async load(): Promise<void> {
    const s = await this.game.refresh();
    this.teams = s.teams;
    this.scoring = normalizeScoring(s.scoring);
    this.eventState = s.event.state;
    this.currentModule = s.event.module;
    this.initPlacements();
    if (!this.mdpTeamId && this.teams.length) this.mdpTeamId = this.teams[0].id;
    if (this.resultModule() === 'mdp') await this.refreshMdpHost();
    await this.buildTeamJoinQrs();
  }

  private initPlacements(): void {
    const defaults = Object.fromEntries(this.teams.map((t, i) => [t.id, i + 1]));
    this.placement = { ...defaults };
    this.dccPlacement = { ...defaults };
    this.chipsPlacement = { ...defaults };
    for (const t of this.teams) {
      this.chipsInputs[t.id] = { correct: '', wrong: 0 };
    }
  }

  selectScoringModule(id: ScoringModuleId): void {
    this.scoringModule.set(id);
    this.scoringSaved.set(false);
  }

  async saveTeam(t: Team): Promise<void> {
    await this.game.apiPatch(`/teams/${t.id}`, {
      name: t.name,
      color: t.color,
      member_count: t.member_count,
    });
    await this.load();
  }

  async saveScoringModule(): Promise<void> {
    const mod = this.scoringModule();
    this.savingScoring.set(true);
    this.scoringSaved.set(false);
    try {
      await this.game.apiPut(`/scoring/${mod}`, { config: this.scoring[mod] });
      this.scoringSaved.set(true);
      await this.load();
    } finally {
      this.savingScoring.set(false);
    }
  }

  async resetAllScores(): Promise<void> {
    if (
      !confirm(
        'Réinitialiser tous les scores et toutes les épreuves ?\n\n' +
          'Les classements repartent à zéro, l\'état de chaque épreuve est effacé ' +
          '(questions/mots redeviennent disponibles).',
      )
    ) {
      return;
    }
    await this.game.apiPost('/reset');
    await this.load();
    await this.refreshMdpHost();
  }

  async resetModule(mod: string): Promise<void> {
    const label = this.resultModules.find((m) => m.id === mod)?.label ?? mod;
    if (
      !confirm(
        `Réinitialiser l'épreuve « ${label} » ?\n\n` +
          'Les points gagnés sur cette épreuve seront retirés. ' +
          'Les autres épreuves ne sont pas affectées.',
      )
    ) {
      return;
    }
    await this.game.apiPost(`/reset/${mod}`);
    await this.load();
    if (mod === 'mdp') await this.refreshMdpHost();
  }

  moduleMeta(id: ScoringModuleId) {
    return SCORING_MODULES.find((m) => m.id === id)!;
  }

  teamName(id: string): string {
    return this.teams.find((t) => t.id === id)?.name ?? id;
  }

  teamColor(id: string): string {
    return this.teams.find((t) => t.id === id)?.color ?? '#888';
  }

  modState(key: string): Record<string, unknown> {
    return (this.eventState[key] as Record<string, unknown>) || {};
  }

  async loadContent(): Promise<void> {
    try {
      this.mdpWords = await this.game.apiGet('/mdp/words');
    } catch {
      this.mdpWords = [];
    }
    try {
      this.dccQuestions = await this.game.apiGet('/dcc/questions');
    } catch {
      this.dccQuestions = [];
    }
  }

  async addMdpWord(): Promise<void> {
    const word = this.newMdpWord.trim();
    if (!word) return;
    await this.game.apiPost('/mdp/words', { words: [word] });
    this.newMdpWord = '';
    this.contentSaved.set(true);
    await this.loadContent();
  }

  async addMdpBulk(): Promise<void> {
    const words = this.newMdpBulk
      .split(/[\n,;]+/)
      .map((w) => w.trim())
      .filter(Boolean);
    if (!words.length) return;
    await this.game.apiPost('/mdp/words', { words });
    this.newMdpBulk = '';
    this.contentSaved.set(true);
    await this.loadContent();
  }

  async deleteMdpWord(id: string): Promise<void> {
    if (!confirm('Supprimer ce mot ?')) return;
    await this.game.apiDelete(`/mdp/words/${id}`);
    await this.loadContent();
  }

  async addDccQuestion(): Promise<void> {
    const n = this.newDccQuestion;
    if (!n.question.trim()) return;
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
    this.newDccQuestion = {
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
    this.contentSaved.set(true);
    await this.loadContent();
  }

  async deleteDccQuestion(id: string): Promise<void> {
    if (!confirm('Supprimer cette question ?')) return;
    await this.game.apiDelete(`/dcc/questions/${id}`);
    await this.loadContent();
  }

  private async buildLinkQrCodes(): Promise<void> {
    const base = environment.publicUrl.replace(/\/$/, '');
    const links = [
      { label: 'Rejoindre (joueurs)', path: '/join' },
      { label: 'Grand écran', path: '/board' },
      { label: 'Animateur', path: '/host' },
    ];
    this.linkQrCodes = await Promise.all(
      links.map(async (l) => {
        const url = `${base}${l.path}`;
        const dataUrl = await QRCode.toDataURL(url, { width: 200, margin: 2 });
        return { ...l, url, dataUrl };
      }),
    );
  }

  private async buildTeamJoinQrs(): Promise<void> {
    const base = environment.publicUrl.replace(/\/$/, '');
    this.teamJoinQrs = await Promise.all(
      this.teams.map(async (t) => {
        const url = `${base}/join?team=${t.id}`;
        const dataUrl = await QRCode.toDataURL(url, { width: 160, margin: 2 });
        return { teamId: t.id, name: t.name, color: t.color, url, dataUrl };
      }),
    );
  }

  copyLink(url: string): void {
    navigator.clipboard?.writeText(url);
  }

  // ─── MDP ───────────────────────────────────────────────────────

  async refreshMdpHost(): Promise<void> {
    try {
      this.mdpHostView = await this.game.apiGet('/mdp/host-view');
    } catch {
      /* */
    }
  }

  async mdpStartTurn(): Promise<void> {
    this.mdpError = '';
    try {
      await this.game.apiPost('/mdp/start-turn', {
        team_id: this.mdpTeamId,
        player_index: this.mdpPlayerIndex,
      });
      await this.refreshMdpHost();
    } catch {
      this.mdpError = 'Impossible de lancer : passage encore en cours ?';
    }
  }

  async mdpForceEnd(): Promise<void> {
    await this.game.apiPost('/mdp/end-turn/force');
    await this.refreshMdpHost();
  }

  async mdpFinalize(): Promise<void> {
    await this.game.apiPost('/mdp/finalize', { placement: this.placement });
    await this.load();
  }

  mdpCanStart(): boolean {
    return this.mdpHostView['can_start'] !== false;
  }

  mdpCurrent(): Record<string, unknown> | null {
    return (this.mdpHostView['current'] as Record<string, unknown>) || null;
  }

  mdpLastTurn(): Record<string, unknown> | null {
    return (this.mdpHostView['last_turn'] as Record<string, unknown>) || null;
  }

  mdpTeamScores(): Record<string, { player: number; words: number; points?: number }[]> {
    return (this.modState('mdp')['team_scores'] as Record<string, { player: number; words: number; points?: number }[]>) || {};
  }

  // ─── DCC ───────────────────────────────────────────────────────

  async dccStart(): Promise<void> {
    await this.game.apiPost('/dcc/start');
    await this.load();
  }

  async dccReveal(): Promise<void> {
    await this.game.apiPost('/dcc/reveal');
    await this.load();
  }

  async dccFinalize(): Promise<void> {
    await this.game.apiPost('/dcc/finalize', { placement: this.dccPlacement });
    await this.load();
  }

  dccResults(): Record<string, { mode: string; correct: boolean; points: number }> {
    return (this.modState('dcc')['results'] as Record<string, { mode: string; correct: boolean; points: number }>) || {};
  }

  // ─── Chips ─────────────────────────────────────────────────────

  async chipsStart(): Promise<void> {
    const flavors = this.flavorsToGuess.split(',').map((f) => f.trim()).filter(Boolean);
    await this.game.apiPost('/chips/start', {
      chip_id: this.selectedChipId,
      flavors_to_guess: flavors,
    });
    await this.load();
  }

  async chipsScoreTeam(teamId: string): Promise<void> {
    const input = this.chipsInputs[teamId];
    await this.game.apiPost('/chips/score', {
      team_id: teamId,
      correct_flavors: input.correct.split(',').map((f) => f.trim()).filter(Boolean),
      wrong_count: input.wrong,
    });
    await this.load();
  }

  async chipsFinalize(): Promise<void> {
    await this.game.apiPost('/chips/finalize', { placement: this.chipsPlacement });
    await this.load();
  }

  chipsResults(): Record<string, { correct: string[]; wrong_count: number; points: number }> {
    return (this.modState('chips')['results'] as Record<string, { correct: string[]; wrong_count: number; points: number }>) || {};
  }

  // ─── Paroles ───────────────────────────────────────────────────

  async parolesStart(): Promise<void> {
    await this.game.apiPost('/paroles/start');
    await this.load();
  }

  async parolesListen(): Promise<void> {
    await this.game.apiPost('/paroles/listen');
    await this.load();
  }

  async parolesScore(): Promise<void> {
    await this.game.apiPost('/paroles/score');
    await this.load();
  }

  // ─── Mölkky / Piscine / Poignards ──────────────────────────────

  async molkkyResult(): Promise<void> {
    await this.game.apiPost('/molkky/result', { placement: this.placement });
    await this.load();
  }

  async piscineResult(): Promise<void> {
    await this.game.apiPost('/piscine/result', { placement: this.placement });
    await this.load();
  }

  async poignardsStart(): Promise<void> {
    await this.game.apiPost('/poignards/start');
    await this.load();
  }
}
