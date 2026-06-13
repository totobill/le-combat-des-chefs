import { Component, OnDestroy, OnInit } from '@angular/core';
import { GameService } from '../../core/game.service';
import { Team } from '../../core/models';

@Component({
  selector: 'app-board',
  standalone: true,
  imports: [],
  templateUrl: './board.component.html',
  styleUrl: './board.component.scss',
})
export class BoardComponent implements OnInit, OnDestroy {
  teams: Team[] = [];
  private pollTimer?: ReturnType<typeof setInterval>;

  constructor(private game: GameService) {}

  async ngOnInit(): Promise<void> {
    this.game.connectWs();
    await this.sync();
    this.pollTimer = setInterval(() => this.sync(), 1000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.game.disconnectWs();
  }

  async sync(): Promise<void> {
    const ws = this.game.state();
    const s = ws ?? (await this.game.refreshPublic());
    this.teams = [...s.teams].sort((a, b) => b.score_total - a.score_total);
  }

  maxScore(): number {
    return Math.max(this.teams[0]?.score_total ?? 0, 1);
  }

  podiumOrder(): (Team | null)[] {
    return [this.teams[1] ?? null, this.teams[0] ?? null, this.teams[2] ?? null];
  }

  medal(i: number): string {
    return ['🥈', '🥇', '🥉'][i];
  }
}
