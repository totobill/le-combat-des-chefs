import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-admin-login',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './admin-login.component.html',
  styleUrl: './admin-login.component.scss',
})
export class AdminLoginComponent {
  password = '';
  error = '';
  loading = false;

  constructor(
    private auth: AuthService,
    private router: Router,
    private route: ActivatedRoute,
  ) {}

  async submit(): Promise<void> {
    this.error = '';
    this.loading = true;
    try {
      await this.auth.loginAdmin(this.password);
      await this.router.navigateByUrl(this.returnUrl());
    } catch {
      this.error = 'Mot de passe incorrect';
    } finally {
      this.loading = false;
    }
  }

  private returnUrl(): string {
    const raw = this.route.snapshot.queryParamMap.get('returnUrl');
    const path = raw?.split('?')[0] ?? '/admin';
    if (path === '/admin' || path === '/host') return raw ?? '/admin';
    return '/admin';
  }
}
