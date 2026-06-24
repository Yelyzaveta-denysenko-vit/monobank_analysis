#!/usr/bin/env python3
"""Admin web panel: budgets, categorization rules, tags.

Rill is read-only, so editing user data is delegated to this small app. After a
change it writes to DuckDB, recomputes derived data if needed, and re-exports the
affected Parquet files — Rill picks up the change automatically (file-watch).
User-facing text is in Ukrainian; code/comments are in English.
"""

import time

import duckdb
from flask import Flask, redirect, render_template_string, request, url_for

import categorize
from config import DB_PATH, RILL_URL, log
from export import export_tables

app = Flask(__name__)


def get_con() -> duckdb.DuckDBPyConnection:
    """Open the DB for writing, with retries. DuckDB allows only one writer per
    file, and the sync container holds the lock while syncing (a few minutes on
    first run due to NBU rate loading). Wait ~30s, then surface a friendly error."""
    for attempt in range(40):
        try:
            return duckdb.connect(DB_PATH)
        except duckdb.IOException:
            if attempt == 39:
                raise
            time.sleep(0.75)


@app.errorhandler(duckdb.IOException)
def db_busy(_e):
    body = """
    <h1>База зайнята синхронізацією</h1>
    <p class="muted">Триває оновлення даних з Monobank (на першому запуску це
    займає кілька хвилин). Оновіть сторінку трохи згодом.</p>
    <p><a href="javascript:location.reload()">Оновити</a></p>
    """
    return page("budgets", body), 503


def categories(con) -> list[tuple]:
    return con.execute(
        "SELECT id, name, group_name FROM categories ORDER BY group_name, name"
    ).fetchall()


def fallback_id(con) -> int:
    row = con.execute("SELECT id FROM categories WHERE name = 'Інше'").fetchone()
    return row[0] if row else 1


def recategorize_and_export(con):
    """Rebuild category_id from the updated rules and export transactions."""
    categorize.assign_categories(con, fallback_id(con))
    export_tables(con, ["transactions", "categorization_rules"])


LAYOUT = """
<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monobank BI — керування</title>
<style>
  body{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1a1a1a}
  header{background:#111;color:#fff;padding:12px 20px}
  header a{color:#bbb;text-decoration:none;margin-right:18px;font-size:15px}
  header a.active{color:#fff;font-weight:600}
  main{max-width:900px;margin:24px auto;padding:0 16px}
  h1{font-size:20px;margin:0 0 16px}
  table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  th,td{text-align:left;padding:9px 12px;border-bottom:1px solid #eee;font-size:14px}
  th{background:#fafafa;font-weight:600}
  form.inline{display:inline}
  .card{background:#fff;border-radius:8px;padding:16px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  input,select{padding:6px 8px;border:1px solid #ccc;border-radius:6px;font-size:14px}
  button{padding:6px 12px;border:0;border-radius:6px;background:#2563eb;color:#fff;font-size:14px;cursor:pointer}
  button.danger{background:#dc2626}
  .muted{color:#888;font-size:13px}
  .row{display:flex;gap:8px;flex-wrap:wrap;align-items:end}
  .row label{display:flex;flex-direction:column;font-size:12px;color:#555;gap:3px}
</style></head><body>
<header>
  <a href="/budgets" class="{{ 'active' if tab=='budgets' }}">Бюджети</a>
  <a href="/rules" class="{{ 'active' if tab=='rules' }}">Правила</a>
  <a href="/tags" class="{{ 'active' if tab=='tags' }}">Теги</a>
  <a href="/dashboards" target="_blank">Дашборди Rill ↗</a>
  <span class="muted" style="float:right">Зміни одразу підхоплюються дашбордами Rill</span>
</header>
<main>{{ body|safe }}</main></body></html>
"""


def page(tab, body):
    return render_template_string(LAYOUT, tab=tab, body=body)


@app.route("/")
def index():
    return redirect(url_for("budgets"))


@app.route("/dashboards")
def dashboards():
    """Redirect to the Rill dashboards."""
    return redirect(RILL_URL)


# --- Budgets ---
@app.route("/budgets", methods=["GET", "POST"])
def budgets():
    con = get_con()
    try:
        if request.method == "POST":
            con.execute(
                "INSERT INTO budgets (category_id, month, limit_uah) VALUES (?, ?, ?)",
                [int(request.form["category_id"]), request.form["month"].strip(),
                 float(request.form["limit_uah"])],
            )
            export_tables(con, ["budgets"])
            return redirect(url_for("budgets"))

        rows = con.execute("""
            SELECT b.id, c.name, b.month, b.limit_uah
            FROM budgets b JOIN categories c ON c.id = b.category_id
            ORDER BY b.month DESC, c.name
        """).fetchall()
        cats = categories(con)
    finally:
        con.close()

    opts = "".join(f'<option value="{i}">{g} / {n}</option>' for i, n, g in cats)
    trs = "".join(
        f"<tr><td>{n}</td><td>{m}</td><td>{lim:,.0f} ₴</td>"
        f'<td><form class="inline" method="post" action="/budgets/delete/{bid}">'
        f'<button class="danger">Видалити</button></form></td></tr>'
        for bid, n, m, lim in rows
    ) or '<tr><td colspan="4" class="muted">Лімітів ще немає</td></tr>'

    body = f"""
    <h1>Бюджети за категоріями</h1>
    <div class="card"><form method="post" class="row">
      <label>Категорія<select name="category_id" required>{opts}</select></label>
      <label>Місяць (РРРР-ММ)<input name="month" placeholder="2026-03" required></label>
      <label>Ліміт, ₴<input name="limit_uah" type="number" step="1" min="0" required></label>
      <button type="submit">Додати</button>
    </form></div>
    <table><tr><th>Категорія</th><th>Місяць</th><th>Ліміт</th><th></th></tr>{trs}</table>
    """
    return page("budgets", body)


@app.route("/budgets/delete/<int:bid>", methods=["POST"])
def budget_delete(bid):
    con = get_con()
    try:
        con.execute("DELETE FROM budgets WHERE id = ?", [bid])
        export_tables(con, ["budgets"])
    finally:
        con.close()
    return redirect(url_for("budgets"))


# --- Categorization rules ---
@app.route("/rules", methods=["GET", "POST"])
def rules():
    con = get_con()
    try:
        if request.method == "POST":
            con.execute(
                "INSERT INTO categorization_rules (pattern, field, category_id, priority) "
                "VALUES (?, ?, ?, ?)",
                [request.form["pattern"].strip(), request.form["field"],
                 int(request.form["category_id"]), int(request.form["priority"])],
            )
            recategorize_and_export(con)
            return redirect(url_for("rules"))

        rows = con.execute("""
            SELECT r.id, r.pattern, r.field, c.name, r.priority
            FROM categorization_rules r LEFT JOIN categories c ON c.id = r.category_id
            ORDER BY r.priority DESC, r.id
        """).fetchall()
        cats = categories(con)
    finally:
        con.close()

    opts = "".join(f'<option value="{i}">{g} / {n}</option>' for i, n, g in cats)
    field_label = {"description": "опис", "merchant": "мерчант"}
    trs = "".join(
        f"<tr><td><code>{p}</code></td><td>{field_label.get(f, f)}</td><td>{n}</td><td>{pr}</td>"
        f'<td><form class="inline" method="post" action="/rules/delete/{rid}">'
        f'<button class="danger">Видалити</button></form></td></tr>'
        for rid, p, f, n, pr in rows
    ) or '<tr><td colspan="5" class="muted">Правил ще немає</td></tr>'

    body = f"""
    <h1>Правила категоризації</h1>
    <p class="muted">Правило з більшим пріоритетом перекриває категорію за MCC. Збіг — за підрядком (без урахування регістру).</p>
    <div class="card"><form method="post" class="row">
      <label>Підрядок<input name="pattern" placeholder="NETFLIX" required></label>
      <label>Поле<select name="field"><option value="description">опис</option><option value="merchant">мерчант</option></select></label>
      <label>Категорія<select name="category_id" required>{opts}</select></label>
      <label>Пріоритет<input name="priority" type="number" value="200" required></label>
      <button type="submit">Додати</button>
    </form></div>
    <table><tr><th>Підрядок</th><th>Поле</th><th>Категорія</th><th>Пріоритет</th><th></th></tr>{trs}</table>
    """
    return page("rules", body)


@app.route("/rules/delete/<int:rid>", methods=["POST"])
def rule_delete(rid):
    con = get_con()
    try:
        con.execute("DELETE FROM categorization_rules WHERE id = ?", [rid])
        recategorize_and_export(con)
    finally:
        con.close()
    return redirect(url_for("rules"))


# --- Tags ---
@app.route("/tags", methods=["GET", "POST"])
def tags():
    con = get_con()
    try:
        if request.method == "POST":
            action = request.form.get("action")
            if action == "create":
                con.execute("INSERT INTO tags (name) VALUES (?) ON CONFLICT DO NOTHING",
                            [request.form["name"].strip()])
            elif action == "assign":
                tag_id = int(request.form["tag_id"])
                field = request.form["field"]
                column = "counter_name" if field == "merchant" else "description"
                pattern = request.form["pattern"].strip()
                con.execute(
                    f"INSERT INTO transaction_tags (transaction_id, tag_id) "
                    f"SELECT id, ? FROM transactions WHERE {column} ILIKE '%' || ? || '%' "
                    f"ON CONFLICT DO NOTHING",
                    [tag_id, pattern],
                )
            export_tables(con, ["tags", "transaction_tags"])
            return redirect(url_for("tags"))

        rows = con.execute("""
            SELECT t.id, t.name, COUNT(tt.transaction_id) AS n
            FROM tags t LEFT JOIN transaction_tags tt ON tt.tag_id = t.id
            GROUP BY t.id, t.name ORDER BY t.name
        """).fetchall()
    finally:
        con.close()

    tag_opts = "".join(f'<option value="{i}">{n}</option>' for i, n, _ in rows)
    trs = "".join(
        f"<tr><td>{n}</td><td>{cnt}</td>"
        f'<td><form class="inline" method="post" action="/tags/delete/{tid}">'
        f'<button class="danger">Видалити</button></form></td></tr>'
        for tid, n, cnt in rows
    ) or '<tr><td colspan="3" class="muted">Тегів ще немає</td></tr>'

    body = f"""
    <h1>Теги</h1>
    <div class="card"><form method="post" class="row">
      <input type="hidden" name="action" value="create">
      <label>Новий тег<input name="name" placeholder="Подорож" required></label>
      <button type="submit">Створити</button>
    </form></div>
    <div class="card"><form method="post" class="row">
      <input type="hidden" name="action" value="assign">
      <label>Тег<select name="tag_id" required>{tag_opts}</select></label>
      <label>Поле<select name="field"><option value="description">опис</option><option value="merchant">мерчант</option></select></label>
      <label>Підрядок<input name="pattern" placeholder="BOLT" required></label>
      <button type="submit">Призначити збігам</button>
    </form><p class="muted">Проставить тег усім транзакціям, де поле містить підрядок (зв'язок M:M).</p></div>
    <table><tr><th>Тег</th><th>Транзакцій</th><th></th></tr>{trs}</table>
    """
    return page("tags", body)


@app.route("/tags/delete/<int:tid>", methods=["POST"])
def tag_delete(tid):
    con = get_con()
    try:
        con.execute("DELETE FROM transaction_tags WHERE tag_id = ?", [tid])
        con.execute("DELETE FROM tags WHERE id = ?", [tid])
        export_tables(con, ["tags", "transaction_tags"])
    finally:
        con.close()
    return redirect(url_for("tags"))


if __name__ == "__main__":
    log("Starting admin panel on :8080")
    app.run(host="0.0.0.0", port=8080)
