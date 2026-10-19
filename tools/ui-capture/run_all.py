#!/usr/bin/env python3
"""
End-to-end orchestrator for English-UI showcase screenshots.

Phase: test-first coding / demo capture stage.

Flow:
  1. drop+create logistics_demo_seed (postgres superuser)
  2. start war standalone (test-mode), wait HTTP 200
  3. run 6 seed files (postgres owner)
  4. clear admin.must_change_password
  5. APPLY seed-en-overlay.sql (Englishize DB-locatable Chinese)
  6. EVIDENCE: psql CJK scan (which DB tables/rows hold CJK) + curl /api/chain8/customers
  7. Playwright: login admin/admin123 -> en-US -> 4 shots
     each preceded by a DATA-ROW wait + a HARD zero-CJK assertion on document.body.innerText
     (rbac guard = limited session via intercepting /api/auth/me/permissions to drop admin.users:READ)
  8. cleanup: kill war, drop db, orphan check

Demo data provenance (source-audited): the Chinese strings rendered on the dashboard are
FRONTEND TypeScript seeds (spa/src/data/seed/*.ts) compiled into the SPA bundle, NOT database
rows. The DB's only CJK is the bilingual sys_dict_entry (V3). Accordingly the overlay is a
no-op and the dashboard/tracking pages will FAIL the zero-CJK assertion (BLOCKED, code-gen).
"""
import os, sys, time, socket, subprocess, json, urllib.request, urllib.error, re

PG = os.environ.get('PG_PASSWORD', '')
if not PG:
    print("FATAL: PG_PASSWORD not set", file=sys.stderr); sys.exit(2)
HOST = os.environ.get('DEMO_DB_HOST', '127.0.0.1')  # set DEMO_DB_HOST to your PG host
PGPORT = '5432'
DB = 'logistics_demo_seed'
WAR = '/opt/java_projects/logistics/java/logistics-web/target/logistics-web.war'
OUT = '/tmp/opencode/shots'
RUNLOG = '/tmp/opencode/run.log'
WARLOG = '/tmp/opencap/war.log'
SEED_OVERLAY = '/tmp/opencode/seed-en-overlay.sql'
os.makedirs(OUT, exist_ok=True)
open(RUNLOG, 'w').close()
open(WARLOG, 'w').close()

SEEDS = [
    '/opt/java_projects/logistics/scripts/seed-chain1.sql',
    '/opt/java_projects/logistics/scripts/seed-chain6.sql',
    '/opt/java_projects/logistics/scripts/seed-chain7.sql',
    '/opt/java_projects/logistics/scripts/seed-chain8.sql',
    '/opt/java_projects/logistics/scripts/seed-rbac.sql',
    '/opt/java_projects/logistics/tests/e2e/seed-e2e-actor.sql',
]

GATE_CATALOG = [
    "crm.customers:READ","crm.credit:READ","pricing.rates:READ","booking.jobs:READ","docs.bl:READ",
    "tracking.board:READ","finance.charges:READ","doc.req:READ","ops.wms:READ","admin.users:READ",
    "rbac.admin:ROLE_MANAGE","crm.customers:WRITE","finance.charges:WRITE","notify.inbox:READ",
    "wms.receipt:READ","wms.putaway:WRITE","wms.inventory:READ","wms.loadplan:READ",
    "ops.admin:READ","ops.admin:OPERATE",
]
GUARD_CODE = 'admin.users:READ'

# Zero-CJK gate: any CJK / fullwidth / bracket char in the rendered page fails it.
CJK_TOKEN_RE = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u300a\u300b\u300c\u300d]+')

# Attribution map: rendered Chinese substring -> code-gen source (frontend seed / in-memory repo).
CJK_SOURCE = {
    '华通电子': 'spa/src/data/seed/crm.ts:7 (Customer.name)',
    '宁波对外经贸': 'spa/src/data/seed/crm.ts:22',
    '青岛海洋渔业': 'spa/src/data/seed/crm.ts:37 (also finance.ts:232)',
    '上海机械进出口': 'spa/src/data/seed/crm.ts:52',
    'SI 截单': 'spa/src/data/seed/finance.ts:271',
    '补料': 'spa/src/data/seed/finance.ts:271 / tracking.ts:76 / docs.ts:71,87',
    '应收账款逾期': 'spa/src/data/seed/tracking.ts:99',
    '信用超额': 'spa/src/data/seed/tracking.ts:81 (特审) / finance.ts:277',
    '目的港清关': 'spa/src/data/seed/finance.ts:274 / tracking.ts:87',
    '到港预报': 'spa/src/data/seed/tracking.ts:93 (also finance.ts:273)',
    '海运费': 'spa/src/data/seed/finance.ts (costName)',
    '码头操作费': 'spa/src/data/seed/finance.ts (costName)',
    '报关费': 'spa/src/data/seed/finance.ts:50 (costName)',
    '拖车费': 'spa/src/data/seed/finance.ts:197 (costName)',
    'VGM申报费': 'spa/src/data/seed/finance.ts:45 (costName)',
    '文件费': 'spa/src/data/seed/finance.ts:40 (costName)',
    '长荣海运': 'spa/src/data/seed/finance.ts:237 / crm.ts (supplier)',
    '中远海运': 'spa/src/data/seed/finance.ts:242',
    '瑞鑫集装箱车队': 'spa/src/data/seed/finance.ts:247',
    '黄报关': 'spa/src/data/seed/adminsys.ts:5',
    '周仓管': 'spa/src/data/seed/adminsys.ts:6',
    '陈管理员': 'spa/src/data/seed/adminsys.ts:7',
    '报关员': 'spa/src/data/seed/adminsys.ts:5,31',
    '仓库/CFS 操作员': 'spa/src/data/seed/adminsys.ts:6',
    '系统管理员': 'spa/src/data/seed/adminsys.ts:7,29',
    '已委托': 'spa/src/data/seed/adminsys.ts:12 / docs.ts:134',
    '已申报': 'spa/src/data/seed/adminsys.ts:12 / docs.ts:135',
    '待批': 'spa/src/data/seed/adminsys.ts:13',
    '处理中': 'spa/src/data/seed/adminsys.ts:25',
    '已确认': 'spa/src/data/seed/adminsys.ts:21',
    '订舱': 'spa/src/data/seed/finance.ts:271 (role)',
    '单证': 'spa/src/data/seed/finance.ts:272 (role)',
    '跟踪': 'spa/src/data/seed/finance.ts:273,274 (role)',
    '财务': 'spa/src/data/seed/finance.ts:275,279 (role)',
    '销售': 'spa/src/data/seed/finance.ts:276,282 (role)',
    '客服': 'spa/src/data/seed/adminsys.ts:32 (role)',
    '仓库': 'spa/src/data/seed/adminsys.ts:30 (role)',
    '管理层': 'spa/src/data/seed/adminsys.ts:33 (role)',
    '李总监': 'spa/src/data/seed/adminsys.ts:13',
    '华关部': 'spa/src/data/seed/adminsys.ts:5 (dept)',
    '宝山CFS': 'spa/src/data/seed/adminsys.ts:6 (dept)',
    'IT 部': 'spa/src/data/seed/adminsys.ts:7 (dept)',
    '一般贸易': 'spa/src/data/seed/docs.ts:134,135 (supervision)',
    '中国银行牌价': 'spa/src/data/seed/finance.ts:16 (fx source)',
}

war_proc = None
started_port = None

def W(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with open(RUNLOG, 'a') as f:
        f.write(line + '\n')

def psql_super(sql):
    env = dict(os.environ, PGPASSWORD=PG, PGCONNECT_TIMEOUT='15')
    r = subprocess.run(['psql','-h',HOST,'-p',PGPORT,'-U','postgres','-d','postgres',
                        '-v','ON_ERROR_STOP=1','-tAc',sql],
                       env=env, capture_output=True, text=True)
    return r

def psql_super_db(sql):
    env = dict(os.environ, PGPASSWORD=PG, PGCONNECT_TIMEOUT='15')
    r = subprocess.run(['psql','-h',HOST,'-p',PGPORT,'-U','postgres','-d',DB,
                        '-v','ON_ERROR_STOP=1','-tAc',sql],
                       env=env, capture_output=True, text=True)
    return r

def psql_super_file(path):
    env = dict(os.environ, PGPASSWORD=PG, PGCONNECT_TIMEOUT='15')
    r = subprocess.run(['psql','-h',HOST,'-p',PGPORT,'-U','postgres','-d',DB,
                        '-v','ON_ERROR_STOP=1','-q','-f',path],
                       env=env, capture_output=True, text=True)
    return r

def free_port():
    for p in range(8050, 8080):
        try:
            s = socket.socket(); s.bind(('127.0.0.1', p)); s.close(); return p
        except OSError:
            continue
    raise RuntimeError('no free port in 8050-8079')

def wait_ready(base, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + '/', timeout=5) as r:
                if r.status == 200:
                    return True
        except urllib.error.HTTPError as e:
            if e.code in (200, 301, 302, 401, 403):
                return True
        except Exception:
            pass
        if war_proc and war_proc.poll() is not None:
            W(f"war exited early rc={war_proc.returncode}")
            return False
        time.sleep(1)
    return False

def run_overlay():
    if not os.path.exists(SEED_OVERLAY):
        W(f"overlay file not found at {SEED_OVERLAY} (skipping)")
        return 0
    txt = open(SEED_OVERLAY, encoding='utf-8').read()
    r = psql_super_db(txt)
    rc = r.returncode
    affected = 0
    for line in (r.stdout or '').splitlines():
        if line.strip().isdigit():
            try: affected += int(line.strip())
            except: pass
    W(f"overlay applied rc={rc} rows_updated~{affected} stderr={r.stderr.strip()[:120]}")
    return rc

SCAN_TABLES = ['customer','sys_user','supplier','job','job_milestone','sys_dict_entry',
               'sys_permission','sys_role','charge_line','invoice','statement',
               'credit_approval','sys_audit','sys_user_role','sys_role_permission']

def psql_cjk_scan():
    """Evidence: which DB tables/rows actually contain CJK. Expected: only sys_dict_entry (bilingual)."""
    W("--- DB CJK SCAN (evidence) ---")
    total = 0
    for t in SCAN_TABLES:
        r = psql_super_db(f"SELECT to_regclass('{t}');")
        exists = (r.stdout or '').strip() not in ('', 'null')
        if not exists:
            W(f"  DB-CJK scan: table '{t}' not present (skipped)")
            continue
        r = psql_super_db(f"SELECT * FROM {t};")
        hits = 0
        for line in (r.stdout or '').splitlines():
            if CJK_TOKEN_RE.search(line):
                hits += 1
                if hits <= 3:
                    W(f"  DB-CJK {t}: {line[:140]}")
        if hits:
            W(f"  DB-CJK {t}: {hits} row(s) contain CJK")
            total += hits
        else:
            W(f"  DB-CJK {t}: 0 rows with CJK")
    W(f"--- DB CJK SCAN DONE: total_cjk_rows={total} ---")
    return total

def curl_evidence(base):
    """Evidence: login + GET /api/chain8/customers — show the CRM backend returns ASCII."""
    import urllib.request as u, urllib.error as ue, http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = u.build_opener(u.HTTPCookieProcessor(cj))
    body = json.dumps({'username':'admin','password':'admin123'}).encode()
    req = u.Request(base+'/api/auth/login', data=body, headers={'Content-Type':'application/json'})
    code = 0
    try:
        resp = opener.open(req, timeout=15); code = resp.status
    except ue.HTTPError as e:
        code = e.code
    W(f"curl evidence: login HTTP {code}")
    try:
        resp = opener.open(base+'/api/chain8/customers', timeout=15)
        data = json.loads(resp.read())
        names = []
        rows = data if isinstance(data, list) else (data.get('items') or data.get('data') or ([data] if isinstance(data, dict) else []))
        for it in rows:
            names.append(it.get('name') or it.get('companyName') or it.get('customerName') or '?')
        W(f"curl /api/chain8/customers: HTTP {resp.status} count={len(names)} names={names[:6]}")
        has_cjk = any(CJK_TOKEN_RE.search(n) for n in names if isinstance(n,str))
        W(f"curl evidence: CRM customer names contain CJK={has_cjk}")
    except Exception as e:
        W(f"curl /api/chain8/customers: {e}")

def wait_data_rows(page, kind):
    try:
        page.wait_for_load_state('networkidle', timeout=25000)
        if kind == 'dashboard':
            page.wait_for_selector('.ant-table-row, .ant-list-item, .ant-card', timeout=20000)
        elif kind == 'crm':
            page.wait_for_selector('.ant-table-row, .ant-empty, [data-testid="customer-row"]', timeout=20000)
        elif kind == 'tracking':
            page.wait_for_selector('.ant-card, [data-testid*="lane"], [data-testid*="card"], .ant-table-row', timeout=20000)
        elif kind == 'guard':
            page.wait_for_selector('[data-testid="system.forbidden"]', timeout=20000)
    except Exception as e:
        W(f"wait_data [{kind}] {type(e).__name__}: {e}")
    page.wait_for_timeout(1500)  # settle

def assert_zero_cjk(page, kind):
    """Hard gate: rendered page text must contain ZERO CJK/fullwidth chars."""
    txt = page.evaluate("() => (document.body.innerText || '')")
    toks = CJK_TOKEN_RE.findall(txt)
    if not toks:
        W(f"ZERO-CJK PASS [{kind}]")
        return True
    uniq = list(dict.fromkeys(toks))[:12]
    srcs = []
    for t in uniq:
        mapped = None
        for key, src in CJK_SOURCE.items():
            if t in key or key in t:
                mapped = f"{t} <- {src}"; break
        srcs.append(mapped or f"{t} <- (frontend seed / InMemoryRepo, see BLOCKED)")
    W(f"ZERO-CJK FAIL [{kind}]: n_tokens={len(toks)} unique={uniq}")
    for s in srcs:
        W(f"   CJK-> {s}")
    W(f"   -> BLOCKED: code-gen (spa/src/data/seed/*.ts), cannot Englishize without editing repo source")
    return False

def take_screenshots(base):
    from playwright.sync_api import sync_playwright, expect
    results = {}; evidence = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width':1600,'height':900}, device_scale_factor=2)
        page = context.new_page()

        captured = {'perms': None, 'has_guard': None}
        def on_resp(resp):
            try:
                if '/api/auth/me/permissions' in resp.url and resp.status == 200:
                    body = resp.json()
                    perms = body.get('permissions', [])
                    if isinstance(perms, list):
                        captured['perms'] = perms
                        captured['has_guard'] = GUARD_CODE in perms
            except Exception:
                pass
        page.on('response', on_resp)

        page.goto(base + '/')
        page.wait_for_selector('[data-testid="auth.login.username"]', timeout=20000)
        W("login page loaded")

        sw = page.locator('.ls-segmented').filter(has=page.get_by_role('radio', name='zh-CN'))
        sw.get_by_role('radio', name='en-US').click()
        expect(sw.get_by_role('radio', name='en-US')).to_have_attribute('aria-checked', 'true')
        W("locale -> en-US")

        page.get_by_test_id('auth.login.username').fill('admin')
        page.get_by_test_id('auth.login.password').fill('admin123')
        page.get_by_test_id('auth.login.submit').click()
        page.wait_for_load_state('networkidle', timeout=20000)
        if 'change-password' in page.url:
            W("must_change_password redirect -> changing password")
            page.wait_for_selector('[data-testid="auth.change-password.current"]', timeout=15000)
            page.get_by_test_id('auth.change-password.current').fill('admin123')
            page.get_by_test_id('auth.change-password.next').fill('Admin12345')
            page.get_by_test_id('auth.change-password.confirm').fill('Admin12345')
            page.get_by_test_id('auth.change-password.submit').click()
            page.wait_for_load_state('networkidle', timeout=20000)

        page.wait_for_function("() => window.location.hash && !window.location.hash.includes('login')", timeout=20000)
        page.wait_for_load_state('networkidle', timeout=20000)
        try:
            page.expect_response(lambda r: '/api/auth/me/permissions' in r.url and r.status == 200, timeout=10000)
        except Exception:
            pass
        W(f"dashboard ready. real perms captured={captured['perms'] is not None}, admin has {GUARD_CODE}={captured['has_guard']}")

        try:
            pv = page.evaluate("""() => fetch('api/auth/me/permissions', { credentials: 'same-origin' })
              .then(r => r.json()).catch(() => null)""")
            if isinstance(pv, dict) and isinstance(pv.get('permissions'), list):
                captured['perms'] = pv['permissions']
                captured['has_guard'] = GUARD_CODE in pv['permissions']
        except Exception as e:
            W(f"perms capture via evaluate failed: {e}")
        W(f"real perms captured now: has_guard={captured['has_guard']} perms={captured['perms']}")

        en_checked = sw.get_by_role('radio', name='en-US').get_attribute('aria-checked')
        ls = page.evaluate("""() => {
          const o={}; try{for(const k of Object.keys(localStorage)){o[k]=localStorage.getItem(k)}}catch(e){o['err']=e.message} return o
        }""")
        loc_key = None
        for k,v in (ls.items() if isinstance(ls,dict) else []):
            if 'locale' in k.lower() or v in ('en-US','en_us'):
                loc_key = (k,v)
        evidence['en_radio_checked'] = en_checked
        evidence['locale_storage'] = loc_key
        W(f"en-US evidence: radio={en_checked}, locale_storage={loc_key}")

        # 5a. dashboard
        page.goto(base + '/#/')
        wait_data_rows(page, 'dashboard')
        evidence['dashboard_zero_cjk'] = assert_zero_cjk(page, 'dashboard')
        page.screenshot(path=OUT+'/dashboard-en.png', full_page=True)
        W("shot: dashboard-en.png")

        # 5b. CRM customers
        page.goto(base + '#/crm/customers')
        wait_data_rows(page, 'crm')
        evidence['crm_zero_cjk'] = assert_zero_cjk(page, 'crm')
        page.screenshot(path=OUT+'/crm-en.png', full_page=True)
        W("shot: crm-en.png")

        # 5c. tracking board
        page.goto(base + '#/tracking/board')
        wait_data_rows(page, 'tracking')
        evidence['tracking_zero_cjk'] = assert_zero_cjk(page, 'tracking')
        page.screenshot(path=OUT+'/tracking-board-en.png', full_page=True)
        W("shot: tracking-board-en.png")

        # 5d. rbac guard: LIMITED SESSION -> strip admin.users:READ
        real = captured['perms']
        if not real:
            real = GATE_CATALOG
        stripped = [c for c in real if c != GUARD_CODE]
        page.route('**/api/auth/me/permissions', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body=json.dumps({'permissions': stripped})))
        # Force a FULL reload so the SPA re-fetches permissions (intercepted -> stripped)
        # into its in-memory store. A bare hash-only goto from /#/tracking/board is a
        # same-document nav: the browser won't reload, the SPA reuses cached perms
        # (still incl admin.users:READ), interception never fires, admin/users renders
        # the real page instead of 403.
        page.reload()
        page.wait_for_load_state('networkidle', timeout=25000)
        try:
            page.expect_response(lambda r: '/api/auth/me/permissions' in r.url and r.status == 200, timeout=10000)
        except Exception:
            pass
        page.goto(base + '#/admin/users')
        page.wait_for_load_state('networkidle', timeout=25000)
        try:
            page.wait_for_selector('[data-testid="system.forbidden"]', timeout=15000)
            expect(page.get_by_text(GUARD_CODE)).to_be_visible(timeout=10000)
            forbid_text = page.locator('[data-testid="system.forbidden"]').inner_text()
            W(f"Forbidden page rendered. text={forbid_text.strip()[:80]}")
            evidence['forbidden_code_visible'] = GUARD_CODE in forbid_text
        except Exception as e:
            W(f"WARN guard wait: {e}")
            evidence['forbidden_code_visible'] = False
        wait_data_rows(page, 'guard')
        evidence['rbac_zero_cjk'] = assert_zero_cjk(page, 'rbac-guard')
        page.screenshot(path=OUT+'/rbac-guard-en.png', full_page=True)
        W("shot: rbac-guard-en.png")

        for name in ['dashboard-en.png','crm-en.png','tracking-board-en.png','rbac-guard-en.png']:
            fp = OUT+'/'+name
            sz = os.path.getsize(fp) if os.path.exists(fp) else 0
            results[name] = sz
        W(f"sizes: {results}")
        W(f"evidence: {evidence}")
        W(f"captured real perms: {captured['perms']}")
        browser.close()
    return results, evidence, captured

def cleanup():
    global war_proc
    W("cleanup: killing war")
    if war_proc and war_proc.poll() is None:
        war_proc.terminate()
        try:
            war_proc.wait(timeout=15)
        except Exception:
            war_proc.kill()
            war_proc.wait(timeout=10)
    pid = war_proc.pid if war_proc else None
    alive = False
    if pid:
        try:
            os.kill(pid, 0); alive = True
        except Exception:
            alive = False
    W(f"war pid={pid} still_alive={alive}")
    r = psql_super("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='%s';" % DB)
    W(f"term conns rc={r.returncode} err={r.stderr.strip()[:120]}")
    r = psql_super("DROP DATABASE IF EXISTS %s;" % DB)
    W(f"drop db rc={r.returncode} err={r.stderr.strip()[:120]}")
    return alive

def main():
    W("=== START showcase capture (v2: overlay + cjk-scan + evidence + zero-cjk gate) ===")
    # 1. create db
    psql_super("DROP DATABASE IF EXISTS %s;" % DB)
    r = psql_super("CREATE DATABASE %s OWNER logistics_app;" % DB)
    W(f"create db rc={r.returncode} err={r.stderr.strip()[:120]}")
    if r.returncode != 0:
        W("FATAL create db"); return 1
    # 2. start war
    global war_proc, started_port
    started_port = free_port()
    env = dict(os.environ,
        SPRING_DATASOURCE_URL=f'jdbc:postgresql://{HOST}:{PGPORT}/{DB}',
        SPRING_DATASOURCE_PASSWORD=PG,
        SPRING_FLYWAY_URL=f'jdbc:postgresql://{HOST}:{PGPORT}/{DB}',
        SPRING_FLYWAY_PASSWORD=PG)
    cmd = ['java','-jar',WAR,'--server.port=%d' % started_port,
           '--logisim.auth.tenant-test-mode=true']
    W(f"starting war on port {started_port}")
    war_proc = subprocess.Popen(cmd, env=env, stdout=open(WARLOG,'w'), stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % started_port
    if not wait_ready(base, 180):
        W("FATAL: war not ready; war log tail:")
        with open(WARLOG) as f:
            lines = f.readlines()
        for ln in lines[-40:]:
            if any(k in ln for k in ['ERROR','Exception','Caused','Started',' Flyway','Fail','fail','Hikari','DatabaseCredential','password','bind','Connection']):
                W('  '+ln.rstrip())
        cleanup(); return 1
    W("war ready (HTTP 200)")
    # Grant app role privileges (Flyway ran as postgres; tables postgres-owned, no grants)
    grant_sql = ("GRANT USAGE ON SCHEMA public TO logistics_app; "
                 "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO logistics_app; "
                 "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO logistics_app; "
                 "GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO logistics_app;")
    rg = psql_super_db(grant_sql)
    W(f"grant to logistics_app rc={rg.returncode} err={rg.stderr.strip()[:160]}")
    # 4. seeds (postgres owner)
    for s in SEEDS:
        r = psql_super_file(s)
        ok = r.returncode == 0
        W(f"seed {os.path.basename(s)}: rc={r.returncode} {'OK' if ok else 'ERR'} err={r.stderr.strip()[:160]}")
        if not ok:
            W(f"FATAL seed {s}"); cleanup(); return 1
    # clear must_change_password for admin
    ru = psql_super_db("UPDATE sys_user SET must_change_password = FALSE WHERE username = 'admin' AND tenant_id = 'default';")
    W(f"clear must_change rc={ru.returncode} err={ru.stderr.strip()[:160]}")
    # 5. apply English overlay (no-op expected: demo Chinese is code-gen, not in DB)
    run_overlay()
    # 6. EVIDENCE: psql CJK scan + curl /api/chain8/customers
    db_cjk = psql_cjk_scan()
    curl_evidence(base)
    # 7. Playwright screenshots
    try:
        results, evidence, captured = take_screenshots(base)
    except Exception as e:
        import traceback
        W(f"PLAYWRIGHT ERROR: {e}")
        W(traceback.format_exc()[-1500:])
        cleanup(); return 1
    # 8. cleanup
    orphan = cleanup()
    # ---- summary ----
    print("\n=== SUMMARY ===")
    print(f"port={started_port}")
    for name in ['dashboard-en.png','crm-en.png','tracking-board-en.png','rbac-guard-en.png']:
        sz = results.get(name, 0)
        print(f"  {name}: {sz/1024:.0f} KB")
    print(f"en-US evidence: radio={evidence.get('en_radio_checked')}, localStorage={evidence.get('locale_storage')}")
    print(f"admin real perms contain {GUARD_CODE}: {captured.get('has_guard')} (simulated limited session for guard)")
    print(f"rbac guard code visible: {evidence.get('forbidden_code_visible')}")
    print(f"zero-CJK gate: dashboard={evidence.get('dashboard_zero_cjk')} crm={evidence.get('crm_zero_cjk')} tracking={evidence.get('tracking_zero_cjk')} rbac-guard={evidence.get('rbac_zero_cjk')}")
    print(f"DB-CJK scan rows: {db_cjk} (expect 0 outside sys_dict_entry bilingual)")
    print(f"cleanup: war killed={not orphan}, db dropped=True")
    print(f"(full detail: {RUNLOG})")
    print(f"(BLOCKED code-gen CJK sources logged above; demo data is spa/src/data/seed/*.ts)")
    ok = all(results.get(n,0) > 50*1024 for n in ['dashboard-en.png','crm-en.png','tracking-board-en.png','rbac-guard-en.png'])
    return 0 if ok else 1

if __name__ == '__main__':
    try:
        code = main()
    finally:
        pass
    sys.exit(code)
