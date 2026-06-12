import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { JsonPipe } from '@angular/common';
import { AuthService } from '../../core/auth.service';
import { GameService } from '../../core/game.service';
import { Team } from '../../core/models';

@Component({
  selector: 'app-host',
  standalone: true,
  imports: [FormsModule, RouterLink, JsonPipe],
  templateUrl: './host.component.html',
  styleUrl: './host.component.scss',
})
export class HostComponent implements OnInit, OnDestroy {
  teams: Team[] = [];
  module = signal<string>('dcc');
  state: Record<string, unknown> = {};

  // MDP
  mdpTeamId = '';
  mdpPlayerIndex = 0;

  // Chips
  chips: { id: string; name: string; flavors: string[] }[] = [];
  selectedChipId = '';
  flavorsToGuess = '';

  // Placement
  placement: Record<string, number> = {};

  // Piscine / Mölkky
  piscinePlacement: Record<string, number> = {};

  constructor(
    public auth: AuthService,
    private game: GameService,
  ) {}

  async ngOnInit(): Promise<void> {
    this.game.connectWs();
    await this.load();
    try {
      this.chips = await this.game.apiGet('/chips');
      if (this.chips.length) this.selectedChipId = this.chips[0].id;
    } catch {
      /* */
    }
    setInterval(() => {
      const s = this.game.state();
      if (s) {
        this.teams = s.teams;
        this.state = s.event.state;
      }
    }, 1500);
  }

  ngOnDestroy(): void {
    this.game.disconnectWs();
  }

  async load(): Promise<void> {
    const s = await this.game.refresh();
    this.teams = s.teams;
    this.state = s.event.state;
    if (!this.mdpTeamId && this.teams.length) this.mdpTeamId = this.teams[0].id;
    this.placement = Object.fromEntries(this.teams.map((t, i) => [t.id, i + 1]));
    this.piscinePlacement = { ...this.placement };
  }

  async startModule(mod: string): Promise<void> {
    this.module.set(mod);
    await this.game.apiPost('/module/start', { module: mod });
    await this.load();
  }

  // DCC
  async dccStart(): Promise<void> {
    await this.game.apiPost('/dcc/start');
  }
  async dccReveal(): Promise<void> {
    await this.game.apiPost('/dcc/reveal');
  }

  // MDP
  async mdpStartTurn(): Promise<void> {
    await this.game.apiPost('/mdp/start-turn', {
      team_id: this.mdpTeamId,
      player_index: this.mdpPlayerIndex,
    });
  }
  async mdpFinalize(): Promise<void> {
    await this.game.apiPost('/mdp/finalize', { placement: this.placement });
  }

  // Paroles
  async parolesStart(): Promise<void> {
    await this.game.apiPost('/paroles/start');
  }
  async parolesListen(): Promise<void> {
    await this.game.apiPost('/paroles/listen');
  }
  async parolesScore(): Promise<void> {
    await this.game.apiPost('/paroles/score');
  }

  // Chips
  async chipsStart(): Promise<void> {
    const flavors = this.flavorsToGuess.split(',').map((f) => f.trim()).filter(Boolean);
    await this.game.apiPost('/chips/start', {
      chip_id: this.selectedChipId,
      flavors_to_guess: flavors,
    });
  }
  async chipsScoreTeam(teamId: string, correct: string, wrong: number): Promise<void> {
    await this.game.apiPost('/chips/score', {
      team_id: teamId,
      correct_flavors: correct.split(',').map((f) => f.trim()).filter(Boolean),
      wrong_count: wrong,
    });
  }

  // Mölkky / Piscine / Poignards
  async molkkyResult(): Promise<void> {
    await this.game.apiPost('/molkky/result', { placement: this.piscinePlacement });
  }
  async piscineResult(): Promise<void> {
    await this.game.apiPost('/piscine/result', { placement: this.piscinePlacement });
  }
  async poignardsStart(): Promise<void> {
    await this.game.apiPost('/poignards/start');
    this.module.set('poignards');
  }

  dccState(): Record<string, unknown> {
    return (this.state['dcc'] as Record<string, unknown>) || {};
  }
  mdpState(): Record<string, unknown> {
    return (this.state['mdp'] as Record<string, unknown>) || {};
  }
  parolesState(): Record<string, unknown> {
    return (this.state['paroles'] as Record<string, unknown>) || {};
  }
  poignardsState(): Record<string, unknown> {
    return (this.state['poignards'] as Record<string, unknown>) || {};
  }
}
