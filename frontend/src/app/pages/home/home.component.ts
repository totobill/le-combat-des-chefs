import { Component, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { GameService } from '../../core/game.service';
import { Team } from '../../core/models';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
})
export class HomeComponent implements OnInit {
  teams: Team[] = [];

  constructor(private game: GameService) {}

  async ngOnInit(): Promise<void> {
    const s = await this.game.refreshPublic();
    this.teams = s.teams;
  }
}
