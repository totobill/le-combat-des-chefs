import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
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
  ) {}

  async submit(): Promise<void> {
    this.error = '';
    this.loading = true;
    try {
      await this.auth.loginAdmin(this.password);
      await this.router.navigate(['/admin']);
    } catch {
      this.error = 'Mot de passe incorrect';
    } finally {
      this.loading = false;
    }
  }
}
