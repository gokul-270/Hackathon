import { describe, test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

function extractFunction(source, funcName) {
    const regex = new RegExp(`export function ${funcName}\\s*\\(([^)]*)\\)\\s*\\{([\\s\\S]*?^})`, 'm');
    const match = source.match(regex);
    if (!match) throw new Error(`Could not find function ${funcName}`);

    const params = match[1];
    const body = match[2];

    const factory = new Function(`
        function ${funcName}(${params}) {
            ${body}
        return ${funcName};
    `);
    return factory();
}

const src = readFileSync(join(__dirname, 'AddEntityModal.mjs'), 'utf-8');

const isValidIp = extractFunction(src, 'isValidIp');
const isDuplicateIp = extractFunction(src, 'isDuplicateIp');

describe('isValidIp', () => {
    test('valid IPs', () => {
        assert.strictEqual(isValidIp('192.168.1.1'), true);
        assert.strictEqual(isValidIp('0.0.0.0'), true);
        assert.strictEqual(isValidIp('255.255.255.255'), true);
    });

    test('invalid IPs', () => {
        assert.strictEqual(isValidIp(''), false);
        assert.strictEqual(isValidIp('192.168.1'), false);
        assert.strictEqual(isValidIp('192.168.1.1.1'), false);
        assert.strictEqual(isValidIp('256.0.0.0'), false);
        assert.strictEqual(isValidIp('192.168.01.1'), false); // leading zero
        assert.strictEqual(isValidIp('abc.def.ghi.jkl'), false);
        assert.strictEqual(isValidIp('192.168.1.-1'), false);
    });
});

describe('isDuplicateIp', () => {
    const existingEntities = [
        { id: 'arm1', ip: '192.168.1.101' },
        { id: 'arm2', ip: '192.168.1.102' }
    ];

    test('returns true for duplicate IP', () => {
        assert.strictEqual(isDuplicateIp('192.168.1.101', existingEntities), true);
        assert.strictEqual(isDuplicateIp('192.168.1.102', existingEntities), true);
    });

    test('returns false for new IP', () => {
        assert.strictEqual(isDuplicateIp('192.168.1.103', existingEntities), false);
    });

    test('handles missing or invalid existing entities', () => {
        assert.strictEqual(isDuplicateIp('192.168.1.103', null), false);
        assert.strictEqual(isDuplicateIp('192.168.1.103', undefined), false);
        assert.strictEqual(isDuplicateIp('192.168.1.103', {}), false);
    });
});
