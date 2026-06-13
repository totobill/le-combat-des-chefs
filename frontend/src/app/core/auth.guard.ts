import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';

export const adminGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.isAdmin()) return true;
  return router.createUrlTree(['/admin/login'], {
    queryParams: { returnUrl: state.url },
  });
};

export const teamGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.isTeam()) return true;
  return router.createUrlTree(['/join']);
};
