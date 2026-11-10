'use strict';

const { createApp } = require('./app');

const port = process.env.PORT || 3000;
const server = createApp().listen(port, () => {
  console.log(`PayFlex API listening on port ${port}`);
});

process.on('SIGTERM', () => server.close(() => process.exit(0)));
process.on('SIGINT', () => server.close(() => process.exit(0)));
