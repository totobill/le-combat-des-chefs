import { Component, OnDestroy, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { GameService } from '../../core/game.service';
import { Team } from '../../core/models';

@Component({
  selector: 'app-board',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './board.component.html',
  styleUrl: './board.component.scss',
})
export class BoardComponent implements OnInit, OnDestroy {
  teams: Team[] = [];
  currentModule: string | null = null;
  poignards: { ranking?: { name: string; color: string; rank: number; handicap_seconds: number }[] } = {};

  constructor(private game: GameService) {}

  async ngOnInit(): Promise<void> {
    this.game.connectWs();
    await this.sync();
    setInterval(() => this.sync(), 2000);
  }

  ngOnDestroy(): void {
    this.game.disconnectWs();
  }

  async sync(): Promise<void> {
    const s = await this.game.refreshPublic();
    this.teams = [...s.teams].sort((a, b) => b.score_total - a.score_total);
    this.currentModule = s.event.module;
    this.poignards = (s.event.state['poignards'] as typeof this.poignards) || {};
  }

  maxScore(): number {
    return this.teams[0]?.score_total || 1;
  }

  podiumOrder(): (Team | null)[] {
    const sorted = this.teams;
    return [sorted[1] ?? null, sorted[0] ?? null, sorted[2] ?? null];
  }

  medal(i: number): string {
    return ['🥈', '🥇', '🥉'][i];
  }
}
