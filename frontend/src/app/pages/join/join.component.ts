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

  constructor(
    private game: GameService,
    private auth: AuthService,
    private router: Router,
    private route: ActivatedRoute,
  ) {}

  async ngOnInit(): Promise<void> {
    const s = await this.game.refreshPublic();
    this.teams = s.teams;
    const teamParam = this.route.snapshot.queryParamMap.get('team');
    if (teamParam && this.teams.some((t) => t.id === teamParam)) {
      this.selectedTeamId = teamParam;
    } else if (this.teams.length) {
      this.selectedTeamId = this.teams[0].id;
    }
  }

  async submit(): Promise<void> {
    this.error = '';
    if (!this.selectedTeamId || !this.displayName.trim()) {
      this.error = 'Choisissez une équipe et entrez votre prénom';
      return;
    }
    this.loading = true;
    try {
      await this.auth.joinTeam(this.selectedTeamId, this.displayName.trim());
      await this.router.navigate(['/team']);
    } catch {
      this.error = 'Impossible de rejoindre — vérifiez le code session';
    } finally {
      this.loading = false;
    }
  }
}
