import { access } from 'node:fs/promises';
import { constants } from 'node:fs';
import { isAbsolute } from 'node:path';

export function validate(schema, value, name = 'parameters') {
  const fail = () => { throw new Error(`INVALID_${name.replace(/[^A-Za-z0-9]/g, '_').toUpperCase()}`); };
  if (schema.type === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) fail();
    if ((schema.required || []).some(k => value[k] === undefined)) fail();
    if (schema.additionalProperties === false && Object.keys(value).some(k => !(k in schema.properties))) fail();
    for (const [key, entry] of Object.entries(value)) if (schema.properties[key]) validate(schema.properties[key], entry, `${name}_${key}`);
  } else if (schema.type === 'array') {
    if (!Array.isArray(value) || value.length < (schema.minItems ?? 0) || value.length > (schema.maxItems ?? Infinity)) fail();
    if (schema.uniqueItems && new Set(value.map(x => JSON.stringify(x))).size !== value.length) fail();
    value.forEach((x, i) => validate(schema.items, x, `${name}_${i}`));
  } else if (schema.type === 'string') {
    if (typeof value !== 'string' || value.length < (schema.minLength ?? 0) || value.length > (schema.maxLength ?? Infinity) || /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(value)) fail();
    if (schema.format === 'date-time' && !Number.isFinite(Date.parse(value))) fail();
  } else if (schema.type === 'integer') {
    if (!Number.isSafeInteger(value) || value < (schema.minimum ?? -Infinity) || value > (schema.maximum ?? Infinity)) fail();
  } else if (schema.type === 'boolean' && typeof value !== 'boolean') fail();
}

export async function validateConfig(schema, config) {
  if (Object.keys(config).length === 0) return { ok: true, warnings: ['Not configured; Teamlink is disabled.'] };
  try {
    validate(schema, config, 'config');
    for (const key of ['nativeCliPath', 'nodePath', 'pythonPath', 'portPath', 't3Home']) {
      if (!isAbsolute(config[key])) throw new Error('ABSOLUTE_INSTALLED_PATH_REQUIRED');
      await access(config[key], ['nodePath','pythonPath'].includes(key) ? constants.X_OK : constants.R_OK);
    }
    return { ok: true };
  } catch (error) { return { ok: false, errors: [/^[A-Z_]+$/.test(error.message) ? error.message : 'INSTALLED_PATH_UNAVAILABLE'] }; }
}
