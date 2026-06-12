import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../core/auth.service';
import { GameService } from '../../core/game.service';
import { Team } from '../../core/models';

@Component({
  selector: 'app-team',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './team.component.html',
  styleUrl: './team.component.scss',
})
export class TeamComponent implements OnInit, OnDestroy {
  myTeam: Team | null = null;
  currentModule: string | null = null;
  eventState: Record<string, unknown> = {};

  // DCC
  dccView: Record<string, unknown> = {};
  dccMode = '';
  dccAnswer: string | number = '';
  cashInput = '';

  // MDP
  mdpView: Record<string, unknown> = {};
  mdpTimer = signal(30);
  private mdpInterval?: ReturnType<typeof setInterval>;

  // Paroles
  parolesView: Record<string, unknown> = {};
  parolesAnswers: string[] = [];

  // Chips
  chipsView: Record<string, unknown> = {};
  chipsGuesses = '';

  constructor(
    public auth: AuthService,
    private game: GameService,
  ) {}

  async ngOnInit(): Promise<void> {
    this.game.connectWs();
    await this.sync();
    setInterval(() => this.sync(), 1500);
  }

  ngOnDestroy(): void {
    if (this.mdpInterval) clearInterval(this.mdpInterval);
  }

  async sync(): Promise<void> {
    const s = await this.game.refresh();
    const tid = this.auth.teamId();
    this.myTeam = s.teams.find((t) => t.id === tid) ?? null;
    this.currentModule = s.event.module;
    this.eventState = s.event.state;

    if (this.currentModule === 'dcc') {
      this.dccView = await this.game.apiGet('/dcc/current');
    }
    if (this.currentModule === 'mdp') {
      this.mdpView = await this.game.apiGet('/mdp/player-view');
      this.setupMdpTimer();
    }
    if (this.currentModule === 'paroles') {
      this.parolesView = await this.game.apiGet('/paroles/view');
      const n = (this.parolesView['blank_count'] as number) || 0;
      if (this.parolesAnswers.length !== n) {
        this.parolesAnswers = Array(n).fill('');
      }
    }
    if (this.currentModule === 'chips') {
      this.chipsView = await this.game.apiGet('/chips/view');
    }
  }

  setupMdpTimer(): void {
    if (!this.mdpView['active']) {
      if (this.mdpInterval) clearInterval(this.mdpInterval);
      return;
    }
    if (this.mdpInterval) return;
    this.mdpTimer.set(30);
    this.mdpInterval = setInterval(() => {
      const v = this.mdpTimer() - 1;
      this.mdpTimer.set(v);
      if (v <= 0) {
        clearInterval(this.mdpInterval);
        this.mdpInterval = undefined;
        this.game.apiPost('/mdp/end-turn').then(() => this.sync());
      }
    }, 1000);
  }

  async dccChoose(mode: string): Promise<void> {
    await this.game.apiPost('/dcc/choose', { mode });
    this.dccMode = mode;
    await this.sync();
  }

  async dccSubmitAnswer(): Promise<void> {
    const mode = this.dccView['mode'] as string;
    let answer: string | number = this.cashInput;
    if (mode === 'duo' || mode === 'carre') {
      answer = this.dccAnswer;
    }
    await this.game.apiPost('/dcc/answer', { answer });
    await this.sync();
  }

  async mdpNextWord(): Promise<void> {
    await this.game.apiPost('/mdp/next-word');
    this.mdpTimer.set(30);
    await this.sync();
  }

  async parolesSubmit(): Promise<void> {
    await this.game.apiPost('/paroles/submit', { answers: this.parolesAnswers });
    await this.sync();
  }

  async chipsSubmit(): Promise<void> {
    const guesses = this.chipsGuesses.split(',').map((g) => g.trim()).filter(Boolean);
    await this.game.apiPost('/chips/guess', { guesses });
    await this.sync();
  }

  dccOpts(): string[] {
    return (this.dccView['options'] as string[]) || [];
  }

  parolesLocked(): boolean {
    const tid = this.auth.teamId();
    const locked = this.parolesView['locked'] as Record<string, boolean> | undefined;
    return !!tid && !!locked?.[tid];
  }

  isDccRevealed(): boolean {
    const dcc = this.eventState['dcc'] as { revealed?: boolean } | undefined;
    return !!dcc?.revealed;
  }
}
