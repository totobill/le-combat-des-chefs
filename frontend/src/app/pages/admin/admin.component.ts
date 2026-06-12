import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { GameService } from '../../core/game.service';
import { Team } from '../../core/models';

const MODULES = ['mdp', 'dcc', 'chips', 'molkky', 'paroles', 'piscine', 'poignards'];

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.scss',
})
export class AdminComponent implements OnInit {
  teams: Team[] = [];
  scoring: Record<string, Record<string, unknown>> = {};
  scoringJson = '';
  tab = signal<'teams' | 'scoring' | 'links'>('teams');
  modules = MODULES;

  constructor(
    public auth: AuthService,
    private game: GameService,
  ) {}

  async ngOnInit(): Promise<void> {
    this.game.connectWs();
    await this.load();
  }

  async load(): Promise<void> {
    const s = await this.game.refresh();
    this.teams = s.teams;
    this.scoring = s.scoring;
    this.scoringJson = JSON.stringify(s.scoring, null, 2);
  }

  async saveTeam(t: Team): Promise<void> {
    await this.game.apiPatch(`/teams/${t.id}`, {
      name: t.name,
      color: t.color,
      member_count: t.member_count,
    });
    await this.load();
  }

  async saveScoringModule(mod: string): Promise<void> {
    try {
      const all = JSON.parse(this.scoringJson) as Record<string, Record<string, unknown>>;
      const cfg = all[mod];
      if (cfg) {
        await this.game.apiPut(`/scoring/${mod}`, { config: cfg });
      }
    } catch {
      alert('JSON invalide');
    }
    await this.load();
  }

  async resetScores(): Promise<void> {
    if (!confirm('Remettre tous les scores à zéro ?')) return;
    await this.game.apiPost('/reset');
    await this.load();
  }
}
