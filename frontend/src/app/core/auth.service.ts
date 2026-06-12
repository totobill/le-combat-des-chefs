import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';

export interface AuthState {
  token: string;
  role: 'admin' | 'team';
  teamId?: string;
  displayName?: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly storageKey = 'combat_auth';
  readonly auth = signal<AuthState | null>(this.load());

  constructor(
    private http: HttpClient,
    private router: Router,
  ) {}

  get token(): string | null {
    return this.auth()?.token ?? null;
  }

  isAdmin(): boolean {
    return this.auth()?.role === 'admin';
  }

  isTeam(): boolean {
    return this.auth()?.role === 'team';
  }

  teamId(): string | null {
    return this.auth()?.teamId ?? null;
  }

  async loginAdmin(password: string): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<{ access_token: string; role: string }>(`${environment.apiUrl}/auth/admin`, {
        password,
      }),
    );
    this.setAuth({ token: res.access_token, role: 'admin' });
  }

  async joinTeam(teamId: string, displayName: string): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<{ access_token: string; role: string; team_id: string; display_name: string }>(
        `${environment.apiUrl}/auth/join`,
        {
          session_code: environment.sessionCode,
          team_id: teamId,
          display_name: displayName,
        },
      ),
    );
    this.setAuth({
      token: res.access_token,
      role: 'team',
      teamId: res.team_id,
      displayName: res.display_name,
    });
  }

  logout(): void {
    localStorage.removeItem(this.storageKey);
    this.auth.set(null);
    this.router.navigate(['/']);
  }

  private setAuth(state: AuthState): void {
    localStorage.setItem(this.storageKey, JSON.stringify(state));
    this.auth.set(state);
  }

  private load(): AuthState | null {
    try {
      const raw = localStorage.getItem(this.storageKey);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }
}
