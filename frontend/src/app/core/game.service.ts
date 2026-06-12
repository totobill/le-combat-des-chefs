import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { GameState } from './models';

@Injectable({ providedIn: 'root' })
export class GameService {
  readonly state = signal<GameState | null>(null);
  private ws: WebSocket | null = null;

  constructor(private http: HttpClient) {}

  async refresh(): Promise<GameState> {
    const s = await firstValueFrom(this.http.get<GameState>(`${environment.apiUrl}/game/state`));
    this.state.set(s);
    return s;
  }

  async refreshPublic(): Promise<GameState> {
    const s = await firstValueFrom(this.http.get<GameState>(`${environment.apiUrl}/game/public`));
    this.state.set(s);
    return s;
  }

  connectWs(): void {
    if (this.ws) return;
    const url = `${environment.wsUrl}/${environment.sessionCode}`;
    this.ws = new WebSocket(url);
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'state_update') {
          this.state.set(msg.state);
        }
      } catch {
        /* ignore */
      }
    };
    this.ws.onclose = () => {
      this.ws = null;
      setTimeout(() => this.connectWs(), 3000);
    };
  }

  disconnectWs(): void {
    this.ws?.close();
    this.ws = null;
  }

  apiPost<T>(path: string, body: unknown = {}): Promise<T> {
    return firstValueFrom(this.http.post<T>(`${environment.apiUrl}/game${path}`, body));
  }

  apiPut<T>(path: string, body: unknown): Promise<T> {
    return firstValueFrom(this.http.put<T>(`${environment.apiUrl}/game${path}`, body));
  }

  apiPatch<T>(path: string, body: unknown): Promise<T> {
    return firstValueFrom(this.http.patch<T>(`${environment.apiUrl}/game${path}`, body));
  }

  apiGet<T>(path: string): Promise<T> {
    return firstValueFrom(this.http.get<T>(`${environment.apiUrl}/game${path}`));
  }
}
