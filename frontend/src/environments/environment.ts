export const environment = {
  production: false,
  apiUrl: '/api',
  wsUrl: `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`,
  sessionCode: 'CHEFS',
  publicUrl: 'http://localhost:4200',
};
