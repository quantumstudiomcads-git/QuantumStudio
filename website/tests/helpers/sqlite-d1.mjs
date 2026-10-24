import {execFileSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {resolve} from 'node:path';
// Execute the actual D1 SQL against SQLite, including conditional updates and
// RETURNING. No mocked entitlement algorithm and no remote/network dependency.
const venv = resolve('..', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const python = process.env.QS_TEST_PYTHON || (existsSync(venv) ? venv : process.platform === 'win32' ? 'python' : 'python3');
const bridge = `import json,sqlite3,sys
p=json.load(sys.stdin)
c=sqlite3.connect(p['db']); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
if 'script' in p:
 c.executescript(p['script']); result={}
elif 'batch' in p:
 result=[]
 with c:
  for item in p['batch']:
   before=c.total_changes
   cursor=c.execute(item['sql'],item['values']); rows=[dict(r) for r in cursor.fetchall()] if cursor.description else []
   result.append({'results':rows,'meta':{'changes':c.total_changes-before}})
else:
 cursor=c.execute(p['sql'],p['values']); rows=[dict(r) for r in cursor.fetchall()] if cursor.description else []
 result={'results':rows,'meta':{'changes':c.total_changes}}
c.commit(); c.close(); print(json.dumps(result))`;
export class SQLiteD1 {
  constructor(path) { this.path = path; }
  invoke(payload) {
    return JSON.parse(execFileSync(python, ['-c', bridge], {input: JSON.stringify({db: this.path, ...payload}), encoding: 'utf8'}));
  }
  script(script) { this.invoke({script}); }
  async batch(statements) { return this.invoke({batch:statements.map((s)=>({sql:s.sql,values:s.values}))}); }
  prepare(sql) {
    const statement = {sql, values: [], bind: (...values) => { statement.values = values; return statement; },
      all: async () => this.invoke({sql, values: statement.values}),
      first: async () => this.invoke({sql, values: statement.values}).results[0] || null,
      run: async () => this.invoke({sql, values: statement.values})};
    return statement;
  }
}

