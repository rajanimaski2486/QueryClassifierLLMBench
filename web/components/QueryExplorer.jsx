"use client";

import { useMemo, useState } from "react";
import { methodLabel, shortModel } from "./format";

const eqSet = (a, b) => {
  const A = new Set(a ?? []);
  const B = new Set(b ?? []);
  return A.size === B.size && [...A].every((x) => B.has(x));
};

const normEnts = (xs) =>
  (xs ?? []).map((e) => e.toLowerCase().trim()).sort();

function Tags({ items, goldItems }) {
  const gold = new Set((goldItems ?? []).map((x) => x.toLowerCase?.() ?? x));
  if (!items?.length) return <span className="muted">—</span>;
  return items.map((x) => (
    <span
      key={x}
      className={`tag ${gold.has(x.toLowerCase?.() ?? x) ? "match" : "miss"}`}
    >
      {x}
    </span>
  ));
}

/* Per-query drill-down: gold labels + every model's parsed output side by
   side; any field that disagrees with gold gets a red wash. */
export default function QueryExplorer({ gold, perQuery, modelKeys }) {
  const [search, setSearch] = useState("");
  const [onlyDisagree, setOnlyDisagree] = useState(false);
  const [selId, setSelId] = useState(gold[0]?.id);

  const wrongCount = useMemo(() => {
    const counts = {};
    for (const g of gold) {
      const outs = perQuery[g.id] ?? {};
      counts[g.id] = modelKeys.filter((k) => {
        const p = outs[k]?.parsed;
        return (
          !p ||
          p.type !== g.gold_type ||
          p.route !== g.gold_route ||
          !eqSet(p.categories, g.gold_categories) ||
          JSON.stringify(normEnts(p.entities)) !==
            JSON.stringify(normEnts(g.gold_entities))
        );
      }).length;
    }
    return counts;
  }, [gold, perQuery, modelKeys]);

  const list = gold.filter((g) => {
    if (search && !g.query.toLowerCase().includes(search.toLowerCase()))
      return false;
    if (onlyDisagree && wrongCount[g.id] === 0) return false;
    return true;
  });

  const g = gold.find((x) => x.id === selId) ?? gold[0];
  const outs = perQuery[g?.id] ?? {};

  return (
    <div className="card">
      <h2>Per-query drill-down</h2>
      <p className="desc">
        Pick a query to compare every model&apos;s output against gold. Red
        cells and tags disagree with the gold label; green tags match.
      </p>
      <div className="row">
        <input
          type="text"
          placeholder="Search queries…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          value={g?.id}
          onChange={(e) => setSelId(e.target.value)}
          style={{ maxWidth: 420 }}
        >
          {list.map((q) => (
            <option key={q.id} value={q.id}>
              {q.id} · {q.query} ({wrongCount[q.id]}/{modelKeys.length} wrong)
            </option>
          ))}
        </select>
        <label className="small">
          <input
            type="checkbox"
            checked={onlyDisagree}
            onChange={(e) => setOnlyDisagree(e.target.checked)}
          />{" "}
          only queries with disagreement
        </label>
      </div>

      {g && (
        <>
          <p style={{ fontSize: 15 }}>
            <strong>“{g.query}”</strong>{" "}
            <span className="muted small">
              {g.id} · {g.len_band} words · anchor {g.anchor} · entity load{" "}
              {g.entity_load} · {g.ambiguity}
            </span>
          </p>
          <table>
            <thead>
              <tr>
                <th>Model · method</th>
                <th>Type</th>
                <th>Categories</th>
                <th>Entities</th>
                <th>Route</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody>
              <tr style={{ fontWeight: 600 }}>
                <td>GOLD</td>
                <td>{g.gold_type}</td>
                <td>
                  {g.gold_categories.map((c) => (
                    <span key={c} className="tag">
                      {c}
                    </span>
                  ))}
                </td>
                <td>
                  {g.gold_entities.length ? (
                    g.gold_entities.map((e) => (
                      <span key={e} className="tag">
                        {e}
                      </span>
                    ))
                  ) : (
                    <span className="muted">none</span>
                  )}
                </td>
                <td>{g.gold_route}</td>
                <td className="muted">—</td>
              </tr>
              {modelKeys.map((k) => {
                const o = outs[k];
                const p = o?.parsed;
                const [model, method] = k.split("|");
                if (!o)
                  return (
                    <tr key={k}>
                      <td>
                        {shortModel(model)} · {methodLabel[method]}
                      </td>
                      <td colSpan={5} className="muted">
                        no result
                      </td>
                    </tr>
                  );
                const typeOk = p?.type === g.gold_type;
                const routeOk = p?.route === g.gold_route;
                const catsOk = eqSet(p?.categories, g.gold_categories);
                const entsOk =
                  JSON.stringify(normEnts(p?.entities)) ===
                  JSON.stringify(normEnts(g.gold_entities));
                return (
                  <tr key={k}>
                    <td>
                      {shortModel(model)}{" "}
                      <span className="muted small">
                        {methodLabel[method]}
                      </span>
                    </td>
                    <td className={typeOk ? "" : "cell-miss"}>
                      {p?.type ?? <span className="muted">∅</span>}
                    </td>
                    <td className={catsOk ? "" : "cell-miss"}>
                      <Tags items={p?.categories} goldItems={g.gold_categories} />
                    </td>
                    <td className={entsOk ? "" : "cell-miss"}>
                      <Tags items={p?.entities} goldItems={g.gold_entities} />
                    </td>
                    <td className={routeOk ? "" : "cell-miss"}>
                      {p?.route ?? <span className="muted">∅</span>}
                    </td>
                    <td className="muted">
                      {o.latency_ms ? `${o.latency_ms} ms` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
