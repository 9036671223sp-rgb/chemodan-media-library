import copy
import datetime as dt
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get('N8N_BASE', '').rstrip('/')
API_KEY = os.environ.get('N8N_API_KEY', '')
WORKFLOW_ID = 'iMagZs46gwN9Q0rZ'
REPORT_PATH = Path(os.environ.get('REPORT', 'automation-results/n8n-v5.3.4-patch-result.json'))
OLD_NAME = 'CHEMODAN NEWS V5.3.3 BRANDED MEDIA — URL DEPLOYED VERIFIED — SAFE MANUAL NO SEND'
NEW_NAME = 'CHEMODAN NEWS V5.3.4 BRANDED MEDIA — PICKER FIXED — SAFE MANUAL NO SEND'
NEW_VERSION = 'V5.3.4_BRANDED_MEDIA_PICKER_FIXED_SAFE_MANUAL_NO_SEND'
EXPECTED_BEFORE_HASH = '968a0d64563767f535b31badd1363c112d02f1b2f842447b4de542e24e95e0e3'
EXPECTED_AFTER_HASH = '4e53152a732c04ddc32a150aa59bb2cbe78b5ede22fee66089d9be1d7a094c29'
EXPECTED_CHANGED_NODES = {
    '02 SETTINGS | безопасность и параметры',
    '12B TEMPLATE SELECTOR | library V2 rotation + final dedupe guard',
    '09B BUILD | Command Center V3.1 request V5.2 STAGE-GUARD',
    '16 OWNER-GATE | INLINE SAFE GUARD V5.2 build EF/B2B or block',
    '08B EXTRACT | очистить полный текст статьи новой новости',
    '16A BUILD | DeepSeek media technical JSON request',
    '17 MEDIA PICKER | V5.3 tag + channel + last 3 covers',
    '18 MEDIA GUARD | V5.3 sendPhoto safety gate',
    '26 FINAL | V5.3 branded media proof + execution log row',
}


def api(method: str, path: str, payload=None):
    url = f"{BASE}/{path.lstrip('/')}"
    data = None
    headers = {'X-N8N-API-KEY': API_KEY, 'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read().decode('utf-8')
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {body[:1000]}") from exc


def workflow_body(workflow):
    return {
        'name': workflow['name'],
        'nodes': workflow['nodes'],
        'connections': workflow['connections'],
        'settings': workflow.get('settings', {}),
    }


def canonical_hash(workflow):
    raw = json.dumps(workflow_body(workflow), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def trigger_counts(workflow):
    schedule = sum('scheduletrigger' in str(n.get('type', '')).lower() for n in workflow.get('nodes', []))
    webhook = sum('webhook' in str(n.get('type', '')).lower() for n in workflow.get('nodes', []))
    return schedule, webhook


def node_map(workflow):
    return {n.get('name'): n for n in workflow.get('nodes', [])}


def replace_required(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"Patch precondition missing: {label}")
    return text.replace(old, new, 1)


def patch_workflow(before):
    result = copy.deepcopy(before)
    result['name'] = NEW_NAME
    old_names = [
        OLD_NAME,
        'CHEMODAN NEWS V5.3.2 BRANDED MEDIA — URL FILLED PREDEPLOY — SAFE NO SEND',
        'CHEMODAN NEWS V5.3 BRANDED MEDIA — SAFE IMPORT — NO SEND DEFAULT',
    ]
    old_versions = [
        'V5.3.3_BRANDED_MEDIA_URL_DEPLOYED_VERIFIED_SAFE_MANUAL_NO_SEND',
        'V5.3.2_BRANDED_MEDIA_URL_FILLED_PREDEPLOY_SAFE_NO_SEND',
        'V5.3_BRANDED_MEDIA_SAFE_IMPORT_NO_SEND_DEFAULT',
    ]

    for node in result.get('nodes', []):
        params = node.get('parameters', {})
        code = params.get('jsCode')
        if not isinstance(code, str):
            continue
        for value in old_names:
            code = code.replace(value, NEW_NAME)
        for value in old_versions:
            code = code.replace(value, NEW_VERSION)

        name = node.get('name')
        if name == '02 SETTINGS | безопасность и параметры':
            anchor = "  media_library_version: 'MEDIA_LIBRARY_V1_32_GITHUB_PAGES_DEPLOYED_VERIFIED_SAFE',\n"
            insert = anchor + "  media_picker_contract_version: 'V5.3.4_DEPLOYED_VERIFIED_ASSET_ACCEPTANCE',\n"
            if 'media_picker_contract_version' not in code:
                code = replace_required(code, anchor, insert, 'settings contract version')
            old = "    media_send_enabled: false,\n    media_library_ready: false,\n    telegram_send_nodes_present: true,"
            new = "    media_send_enabled: false,\n    media_library_ready: true,\n    telegram_send_nodes_present: true,"
            code = replace_required(code, old, new, 'owner gate media_library_ready')

        if name == '17 MEDIA PICKER | V5.3 tag + channel + last 3 covers':
            old = "  const readyPool = poolAll.filter(x => x.ready === true && txt(x.approval_status).toUpperCase() === 'APPROVED' && /^https:\\/\\//i.test(txt(x.image_url)));"
            new = """  function assetIsReady(x){
  const approval = txt(x.approval_status).toUpperCase();
  const deployment = txt(x.deployment_status).toUpperCase();
  const technical = txt(x.technical_validation).toUpperCase();
  const approvedOrVerified = approval === 'APPROVED' || (approval.includes('DEPLOYED') && approval.includes('VERIFIED'));
  return x.ready === true && x.local_asset_ready === true && technical === 'PASSED' && deployment === 'LIVE_HTTPS_PAGES' && approvedOrVerified && /^https:\/\//i.test(txt(x.image_url));
}
const readyPool = poolAll.filter(assetIsReady);"""
            if 'const readyPool = poolAll.filter(assetIsReady);' not in code:
                code = replace_required(code, old, new, 'media picker ready pool')

        if name == '18 MEDIA GUARD | V5.3 sendPhoto safety gate':
            anchor = "  if (row.image_ready !== true) return block(row, 'NO_APPROVED_READY_IMAGE: ' + txt(row.media_picker_status));\n"
            insert = anchor + "  const imageApproval = txt(row.image_approval_status).toUpperCase();\n  const imageApprovalOk = imageApproval === 'APPROVED' || (imageApproval.includes('DEPLOYED') && imageApproval.includes('VERIFIED'));\n  if (!imageApprovalOk) return block(row, 'IMAGE_APPROVAL_OR_DEPLOYMENT_PROOF_INVALID: ' + imageApproval);\n"
            if 'IMAGE_APPROVAL_OR_DEPLOYMENT_PROOF_INVALID' not in code:
                code = replace_required(code, anchor, insert, 'media guard deployment proof')

        if name == '26 FINAL | V5.3 branded media proof + execution log row':
            old = "  next_step: blocked.length ? 'Populate and approve real media assets, then separately approve both media gates for manual testing.' : 'Keep Active/Schedule/Webhook disabled; perform manual visual verification.'"
            new = "  next_step: blocked.length ? 'Media assets are deployed and verified. Keep media_send_enabled, owner_gate_approved and final_publication_approved false until a separately authorized manual test.' : 'Keep Active/Schedule/Webhook disabled; perform manual visual verification.'"
            if old in code:
                code = code.replace(old, new, 1)
        params['jsCode'] = code
    return result


def validate_safety(workflow):
    schedule, webhook = trigger_counts(workflow)
    if workflow.get('active') is not False:
        raise RuntimeError('Workflow active flag is not false')
    if schedule or webhook:
        raise RuntimeError(f'Forbidden triggers found: schedule={schedule}, webhook={webhook}')
    if len(workflow.get('nodes', [])) != 44:
        raise RuntimeError(f"Unexpected node count: {len(workflow.get('nodes', []))}")
    all_code = '\n'.join(str(n.get('parameters', {}).get('jsCode', '')) for n in workflow.get('nodes', []))
    required = [
        'media_send_enabled: false',
        'owner_gate_approved: false',
        'final_publication_approved: false',
        'public_send_enabled: false',
        '43zqbbUUgZSgr8yu',
        'const readyPool = poolAll.filter(assetIsReady);',
        'IMAGE_APPROVAL_OR_DEPLOYMENT_PROOF_INVALID',
    ]
    missing = [x for x in required if x not in all_code]
    if missing:
        raise RuntimeError(f'Missing required safety markers: {missing}')
    telegram_nodes = [n for n in workflow.get('nodes', []) if 'telegram' in str(n.get('type', '')).lower()]
    if len(telegram_nodes) != 1:
        raise RuntimeError(f'Unexpected Telegram node count: {len(telegram_nodes)}')
    telegram_blob = json.dumps(telegram_nodes[0], ensure_ascii=False).lower()
    if 'sendphoto' not in telegram_blob:
        raise RuntimeError('Telegram node is not sendPhoto')
    if 'frolova_turagent' in telegram_blob:
        raise RuntimeError('Forbidden publication target found in Telegram node')


def main():
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        'status': 'FAIL',
        'operation': 'PATCH_V5.3.3_TO_V5.3.4_SAFE',
        'workflow_id': WORKFLOW_ID,
        'backup_mode': None,
        'backup_workflow_id': None,
        'rollback_performed': False,
        'error': None,
    }
    before = None
    try:
        if not API_KEY:
            raise RuntimeError('N8N_API_KEY is empty or unavailable')
        before = api('GET', f'workflows/{WORKFLOW_ID}')
        before_hash = canonical_hash(before)
        report['before'] = {
            'name': before.get('name'),
            'active': before.get('active'),
            'node_count': len(before.get('nodes', [])),
            'canonical_sha256': before_hash,
        }
        schedule_before, webhook_before = trigger_counts(before)
        if before.get('active') is not False or schedule_before or webhook_before:
            raise RuntimeError('Preflight safety failed before patch')

        if before.get('name') == NEW_NAME and before_hash == EXPECTED_AFTER_HASH:
            validate_safety(before)
            report.update({'status': 'PASS', 'result': 'ALREADY_PATCHED_AND_VERIFIED', 'after': report['before']})
            return
        if before.get('name') != OLD_NAME:
            raise RuntimeError(f"Unexpected source workflow name: {before.get('name')}")
        if before_hash != EXPECTED_BEFORE_HASH:
            raise RuntimeError(f'Current workflow hash differs from approved V5.3.3: {before_hash}')

        backup_payload = workflow_body(before)
        backup_payload['name'] = f"{OLD_NAME} — BACKUP BEFORE V5.3.4 — {dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        try:
            backup = api('POST', 'workflows', backup_payload)
            backup_id = backup.get('id')
            if not backup_id:
                raise RuntimeError('Backup API response has no id')
            backup_check = api('GET', f'workflows/{backup_id}')
            backup_hash_as_source = canonical_hash({**backup_check, 'name': before['name']})
            if backup_check.get('active') is not False or backup_hash_as_source != before_hash:
                raise RuntimeError('Backup verification failed')
            report['backup_mode'] = 'N8N_INACTIVE_DUPLICATE'
            report['backup_workflow_id'] = backup_id
        except Exception as backup_error:
            report['backup_mode'] = 'APPROVED_V5.3.3_ARTIFACT_PLUS_ATOMIC_ROLLBACK'
            report['backup_error'] = str(backup_error)[:1000]

        patched = patch_workflow(before)
        before_nodes = node_map(before)
        after_nodes = node_map(patched)
        changed = {name for name in before_nodes if before_nodes[name] != after_nodes.get(name)}
        if changed != EXPECTED_CHANGED_NODES:
            raise RuntimeError(f'Unexpected changed node set: {sorted(changed)}')
        if before.get('connections') != patched.get('connections') or before.get('settings') != patched.get('settings'):
            raise RuntimeError('Connections or workflow settings changed unexpectedly')
        if canonical_hash(patched) != EXPECTED_AFTER_HASH:
            raise RuntimeError(f"Patched payload hash mismatch: {canonical_hash(patched)}")

        api('PUT', f'workflows/{WORKFLOW_ID}', workflow_body(patched))
        after = api('GET', f'workflows/{WORKFLOW_ID}')
        after_hash = canonical_hash(after)
        if after_hash != EXPECTED_AFTER_HASH:
            raise RuntimeError(f'Post-update hash mismatch: {after_hash}')
        if after.get('name') != NEW_NAME:
            raise RuntimeError(f"Post-update name mismatch: {after.get('name')}")
        validate_safety(after)
        report.update({
            'status': 'PASS',
            'result': 'PATCHED_AND_VERIFIED',
            'changed_nodes': sorted(changed),
            'after': {
                'name': after.get('name'),
                'active': after.get('active'),
                'node_count': len(after.get('nodes', [])),
                'canonical_sha256': after_hash,
                'schedule_trigger_count': trigger_counts(after)[0],
                'webhook_count': trigger_counts(after)[1],
            },
        })
    except Exception as exc:
        report['error'] = str(exc)
        if before is not None:
            try:
                current = api('GET', f'workflows/{WORKFLOW_ID}')
                if canonical_hash(current) not in {canonical_hash(before), EXPECTED_AFTER_HASH}:
                    api('PUT', f'workflows/{WORKFLOW_ID}', workflow_body(before))
                    rolled = api('GET', f'workflows/{WORKFLOW_ID}')
                    report['rollback_performed'] = canonical_hash(rolled) == canonical_hash(before)
            except Exception as rollback_error:
                report['rollback_error'] = str(rollback_error)[:1000]
        raise
    finally:
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
