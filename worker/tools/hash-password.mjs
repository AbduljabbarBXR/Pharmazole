import { randomBytes, pbkdf2Sync } from 'node:crypto';

const pw = process.argv[2];
if (!pw) {
  console.log('Usage: node tools/hash-password.mjs <new-password>');
  process.exit(1);
}
const salt = randomBytes(16).toString('base64');
const iter = 100000;
const hash = pbkdf2Sync(pw, Buffer.from(salt, 'base64'), iter, 32, 'sha256').toString('base64');
console.log(`pbkdf2$${iter}$${salt}$${hash}`);
