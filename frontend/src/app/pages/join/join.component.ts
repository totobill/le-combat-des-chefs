import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { GameService } from '../../core/game.service';
import { Team } from '../../core/models';

@Component({
  selector: 'app-join',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './join.component.html',
  styleUrl: './join.component.scss',
})
export class JoinComponent implements OnInit {
  teams: Team[] = [];
  selectedTeamId = '';
  displayName = '';
  error = '';
  loading = false;
  showExistingSession = false;

  constructor(
    private game: GameService,
    public auth: AuthService,
    private router: Router,
    private route: ActivatedRoute,
  ) {}

  async ngOnInit(): Promise<void> {
    if (this.route.snapshot.queryParamMap.get('reset') === '1') {
      this.auth.logout(false);
    }

    const s = await this.game.refreshPublic();
    this.teams = s.teams;
    const teamParam = this.route.snapshot.queryParamMap.get('team');
    if (teamParam && this.teams.some((t) => t.id === teamParam)) {
      this.selectedTeamId = teamParam;
    }

    this.showExistingSession = this.auth.isTeam();
  }

  existingTeamName(): string {
    const tid = this.auth.teamId();
    return this.teams.find((t) => t.id === tid)?.name ?? 'votre équipe';
  }

  continueAsCurrent(): void {
    void this.router.navigate(['/team']);
  }

  switchPlayer(): void {
    this.auth.logout(false);
    this.showExistingSession = false;
    this.displayName = '';
  }

  async submit(): Promise<void> {
    this.error = '';
    if (!this.selectedTeamId) {
      this.error = 'Choisissez votre équipe';
      return;
    }
    if (!this.displayName.trim()) {
      this.error = 'Entrez votre prénom';
      return;
    }
    this.loading = true;
    try {
      await this.auth.joinTeam(this.selectedTeamId, this.displayName.trim());
      try {
        await this.game.apiPost('/mdp/present');
      } catch {
        /* présence MDP optionnelle */
      }
      await this.router.navigate(['/team']);
    } catch {
      this.error = 'Impossible de rejoindre — vérifiez le code session';
    } finally {
      this.loading = false;
    }
  }
}
