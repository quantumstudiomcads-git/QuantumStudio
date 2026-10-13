#!/usr/bin/env node
/* Operator-only D1 helper: no credentials, no licence signing, and no CI PII output. */
import {existsSync, mkdirSync, writeFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

// Kept in sync with functions/_lib/workflow.js so this operator process does
// not change the website package's module mode just to import a worker module.
const APPLICATION_STATUSES = Object.freeze(['APPLIED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'LICENSE_ISSUED', 'EXPIRED', 'REVOKED']);
const transitions = Object.freeze({
  APPLIED: new Set(['UNDER_REVIEW', 'REVOKED']),
  UNDER_REVIEW: new Set(['APPROVED', 'REJECTED', 'REVOKED']),
  APPROVED: new Set(['LICENSE_ISSUED', 'REVOKED']),
  LICENSE_ISSUED: new Set(['EXPIRED', 'REVOKED']),
  EXPIRED: new Set(['REVOKED']), REJECTED: new Set(), REVOKED: new Set(),
});
function assertTransition(oldStatus, newStatus) {
  if (!APPLICATION_STATUSES.includes(oldStatus) || !APPLICATION_STATUSES.includes(newStatus) || !transitions[oldStatus].has(newStatus)) throw new Error(`Invalid application state transition: ${oldStatus} -> ${newStatus}`);
}

const database = 'quantum-studio-beta';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const command = args[0];
const option = (name) => { const index = args.indexOf(name); return index >= 0 ? args[index + 1] : undefined; };
const flag = (name) => args.includes(name);
function fail(message) { process.stderr.write(`${message}\n`); process.exit(2); }
function applicationId(value) { if (!value || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)) fail('Use a UUID application ID.'); return value; }
function quoted(value) { return `'${String(value).replaceAll("'", "''")}'`; }
function environment() { const value = option('--environment') ?? 'local'; if (!['local', 'production'].includes(value)) fail('Use --environment local or --environment production.'); if (value === 'production' && !flag('--production')) fail('Production requires the explicit --production flag.'); return value; }

if (!command || flag('--help')) { process.stdout.write('Usage: node scripts/beta-admin.mjs <list|inspect|transition|record-licence|export|anonymize> [options]\n'); process.exit(command ? 0 : 2); }
if (process.env.CI) fail('Operator tooling refuses to print or export applicant records in CI.');
const selectedEnvironment = environment();
const remote = selectedEnvironment === 'production';
function runD1(sql) {
  const wrangler = resolve(root, 'node_modules/wrangler/bin/wrangler.js');
  if (!existsSync(wrangler)) fail('Wrangler is not installed. Run npm ci first.');
  const result = spawnSync(process.execPath, [wrangler, 'd1', 'execute', database, remote ? '--remote' : '--local', '--config', 'wrangler.toml', '--command', sql, '--json'], {cwd: root, encoding: 'utf8'});
  if (result.status !== 0) fail(result.stderr || result.stdout || 'D1 command failed.');
  try { return JSON.parse(result.stdout); } catch { return result.stdout; }
}
function rows(result) { return Array.isArray(result) && Array.isArray(result[0]?.results) ? result[0].results : []; }
function actor() { const value = option('--actor'); if (!value || value.length > 120) fail('An operator reference of at most 120 characters is required via --actor.'); return value; }
function now() { return new Date().toISOString(); }
function getApplication(id) { const record = rows(runD1(`SELECT application_id, full_name, email, institution, country, academic_role, research_area, intended_evaluation, operating_system, privacy_consent, privacy_version, terms_consent, terms_version, communications_consent, status, submitted_at, updated_at, reviewed_at, review_note, licence_id, licence_issued_at, licence_expires_at, revoked_at FROM beta_applications WHERE application_id = ${quoted(id)};`))[0]; if (!record) fail('Application not found.'); return record; }
function auditSql(id, eventType, actorReference, oldStatus, newStatus, metadata = '{}') { return `INSERT INTO beta_audit_events (event_id, application_id, event_type, event_timestamp, actor_reference, old_status, new_status, metadata_json) VALUES (${quoted(crypto.randomUUID())}, ${quoted(id)}, ${quoted(eventType)}, ${quoted(now())}, ${quoted(actorReference)}, ${oldStatus ? quoted(oldStatus) : 'NULL'}, ${newStatus ? quoted(newStatus) : 'NULL'}, ${quoted(metadata)});`; }

if (command === 'list') {
  const status = option('--status'); if (status && !APPLICATION_STATUSES.includes(status)) fail('Unknown status.');
  const where = status ? `WHERE status = ${quoted(status)}` : '';
  process.stdout.write(`${JSON.stringify(rows(runD1(`SELECT application_id, status, submitted_at, updated_at, reviewed_at, licence_issued_at, licence_expires_at, revoked_at FROM beta_applications ${where} ORDER BY submitted_at DESC LIMIT 500;`)), null, 2)}\n`);
} else if (command === 'inspect') {
  process.stdout.write(`${JSON.stringify(getApplication(applicationId(option('--application'))), null, 2)}\n`);
} else if (command === 'transition') {
  const id = applicationId(option('--application')); const nextStatus = option('--to'); const operator = actor(); if (!APPLICATION_STATUSES.includes(nextStatus)) fail('Unknown target status.');
  const record = getApplication(id); try { assertTransition(record.status, nextStatus); } catch (error) { fail(error instanceof Error ? error.message : 'Invalid transition.'); }
  const timestamp = now(); const reviewColumns = ['UNDER_REVIEW', 'APPROVED', 'REJECTED'].includes(nextStatus) ? `, reviewed_at = ${quoted(timestamp)}` : ''; const revokeColumns = nextStatus === 'REVOKED' ? `, revoked_at = ${quoted(timestamp)}` : '';
  runD1(`BEGIN IMMEDIATE; UPDATE beta_applications SET status = ${quoted(nextStatus)}, updated_at = ${quoted(timestamp)}${reviewColumns}${revokeColumns} WHERE application_id = ${quoted(id)} AND status = ${quoted(record.status)}; ${auditSql(id, 'STATUS_CHANGED', operator, record.status, nextStatus, JSON.stringify({schema: 1}))} COMMIT;`);
  process.stdout.write(`Recorded ${record.status} -> ${nextStatus} for ${id}.\n`);
} else if (command === 'record-licence') {
  const id = applicationId(option('--application')); const operator = actor(); const licenceId = option('--licence-id'); const expiresAt = option('--expires-at');
  if (!licenceId || licenceId.length > 160 || !expiresAt || Number.isNaN(Date.parse(expiresAt))) fail('Use --licence-id and an ISO-8601 --expires-at value.');
  const record = getApplication(id); try { assertTransition(record.status, 'LICENSE_ISSUED'); } catch (error) { fail(error instanceof Error ? error.message : 'Invalid transition.'); }
  const timestamp = now(); runD1(`BEGIN IMMEDIATE; UPDATE beta_applications SET status = 'LICENSE_ISSUED', licence_id = ${quoted(licenceId)}, licence_issued_at = ${quoted(timestamp)}, licence_expires_at = ${quoted(new Date(expiresAt).toISOString())}, updated_at = ${quoted(timestamp)} WHERE application_id = ${quoted(id)} AND status = 'APPROVED'; ${auditSql(id, 'LICENCE_ISSUED_RECORDED', operator, 'APPROVED', 'LICENSE_ISSUED', JSON.stringify({schema: 1}))} COMMIT;`);
  process.stdout.write(`Recorded licence issuance for ${id}; this command does not sign or send a licence.\n`);
} else if (command === 'export') {
  const status = option('--status'); if (status && !APPLICATION_STATUSES.includes(status)) fail('Unknown status.'); const where = status ? `WHERE status = ${quoted(status)}` : '';
  const result = rows(runD1(`SELECT application_id, full_name, email, institution, country, academic_role, research_area, intended_evaluation, operating_system, privacy_consent, privacy_version, terms_consent, terms_version, communications_consent, status, submitted_at, updated_at, reviewed_at, review_note, licence_id, licence_issued_at, licence_expires_at, revoked_at FROM beta_applications ${where} ORDER BY submitted_at DESC;`));
  const directory = resolve(root, 'applicant-exports'); mkdirSync(directory, {recursive: true}); const destination = resolve(directory, `beta-applications-${new Date().toISOString().replaceAll(':', '-')}.json`);
  writeFileSync(destination, `${JSON.stringify(result, null, 2)}\n`, {encoding: 'utf8', mode: 0o600}); process.stdout.write(`Exported ${result.length} record(s) to ignored local file ${destination}.\n`);
} else if (command === 'anonymize') {
  const id = applicationId(option('--application')); const operator = actor(); if (!flag('--confirm-delete')) fail('Anonymization is destructive. Repeat with --confirm-delete after authorization is verified.'); getApplication(id);
  const timestamp = now(); const deletedEmail = `deleted-${id}@example.invalid`;
  runD1(`BEGIN IMMEDIATE; UPDATE beta_applications SET full_name = 'Deleted applicant', email = ${quoted(deletedEmail)}, normalized_email = ${quoted(deletedEmail)}, email_lookup_hash = ${quoted(`deleted:${id}`)}, institution = 'Deleted', country = 'Deleted', academic_role = NULL, research_area = 'Deleted', intended_evaluation = NULL, review_note = NULL, communications_consent = 0, updated_at = ${quoted(timestamp)} WHERE application_id = ${quoted(id)}; ${auditSql(id, 'APPLICATION_ANONYMIZED', operator, null, null, JSON.stringify({schema: 1}))} COMMIT;`);
  process.stdout.write(`Anonymized ${id}; audit events remain without applicant content.\n`);
} else { fail('Unknown command.'); }
