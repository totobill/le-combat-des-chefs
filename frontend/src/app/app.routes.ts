import { Routes } from '@angular/router';
import { adminGuard, teamGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: '', loadComponent: () => import('./pages/home/home.component').then((m) => m.HomeComponent) },
  { path: 'join', loadComponent: () => import('./pages/join/join.component').then((m) => m.JoinComponent) },
  {
    path: 'admin/login',
    loadComponent: () => import('./pages/admin-login/admin-login.component').then((m) => m.AdminLoginComponent),
  },
  {
    path: 'admin',
    canActivate: [adminGuard],
    loadComponent: () => import('./pages/admin/admin.component').then((m) => m.AdminComponent),
  },
  {
    path: 'host',
    canActivate: [adminGuard],
    loadComponent: () => import('./pages/host/host.component').then((m) => m.HostComponent),
  },
  {
    path: 'team',
    canActivate: [teamGuard],
    loadComponent: () => import('./pages/team/team.component').then((m) => m.TeamComponent),
  },
  { path: 'board', loadComponent: () => import('./pages/board/board.component').then((m) => m.BoardComponent) },
  { path: '**', redirectTo: '' },
];
