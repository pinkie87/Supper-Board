/*
 * Verbindung zwischen Board und eigenem Server.
 *
 * Das Board wurde ursprünglich als Claude-Artifact geschrieben und erwartet
 * window.claude.use("db") mit einer kleinen, Firestore-ähnlichen Schnittstelle.
 * Diese Datei stellt genau diese Schnittstelle bereit, speichert aber auf dem
 * eigenen Server (REST) und bekommt Änderungen live per Server-Sent Events.
 */
(function () {
  "use strict";

  function err(code, message) { var e = new Error(message); e.code = code; return e; }

  async function api(method, url, body) {
    var res;
    try {
      res = await fetch(url, {
        method: method,
        headers: body !== undefined ? { "Content-Type": "application/json" } : {},
        body: body !== undefined ? JSON.stringify(body) : undefined,
        credentials: "same-origin"
      });
    } catch (e) { throw err("unavailable", "Keine Verbindung zum Server"); }
    if (res.status === 404) throw err("not_found", "Nicht gefunden");
    var data = null;
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) throw err(res.status >= 500 ? "unavailable" : "failed", (data && (data.detail || data.message)) || ("Fehler " + res.status));
    return data;
  }

  function split(path) { var p = path.split("/"); return { col: p[0], id: p[1] }; }
  function freeze(o) { return o === undefined ? undefined : JSON.parse(JSON.stringify(o)); }

  function docSnap(id, data) {
    if (data) { data = freeze(data); delete data.id; }
    return { id: id, exists: !!data, data: function () { return freeze(data); }, metadata: { fromCache: false, hasPendingWrites: false } };
  }
  function colSnap(list) {
    var docs = list.map(function (d) { return docSnap(d.id, d); });
    return { docs: docs, size: docs.length, empty: !docs.length, docChanges: function () { return []; }, metadata: { fromCache: false, hasPendingWrites: false } };
  }

  // ---------- Live-Abos ----------
  var listeners = []; // {kind:"doc"|"col", col, id, next, error}
  var pending = {};
  function refresh(l) {
    var key = l.kind + ":" + l.col + "/" + (l.id || "");
    if (pending[key]) { pending[key].again = true; return; }
    pending[key] = { again: false };
    var run = function () {
      var p = l.kind === "col" ? api("GET", "/api/db/" + l.col) : api("GET", "/api/db/" + l.col + "/" + l.id + "?missing=null");
      p.then(function (data) {
        listeners.filter(function (x) { return x.kind === l.kind && x.col === l.col && x.id === l.id; }).forEach(function (x) {
          x.next(l.kind === "col" ? colSnap(data) : docSnap(l.id, data));
        });
      }).catch(function (e) { if (l.error) l.error(e); }).finally(function () {
        var again = pending[key].again; delete pending[key];
        if (again) refresh(l);
      });
    };
    run();
  }

  var source = null;
  function connect() {
    if (source || !window.EventSource) return;
    source = new EventSource("/api/events");
    var wasDown = false;
    source.onmessage = function (ev) {
      var e; try { e = JSON.parse(ev.data); } catch (x) { return; }
      var seen = {};
      listeners.forEach(function (l) {
        if (l.col !== e.col) return;
        if (l.kind === "doc" && l.id !== e.id) return;
        var key = l.kind + ":" + l.col + "/" + (l.id || "");
        if (seen[key]) return; seen[key] = true;
        refresh(l);
      });
    };
    source.onerror = function () { wasDown = true; };
    source.onopen = function () {
      // Nach einem Verbindungsabbruch alles neu laden, damit nichts verpasst wird.
      if (wasDown) { wasDown = false; var seen = {}; listeners.forEach(function (l) { var k = l.kind + l.col + l.id; if (!seen[k]) { seen[k] = 1; refresh(l); } }); }
    };
  }

  function subscribe(l) {
    listeners.push(l); connect(); refresh(l);
    return function () { listeners = listeners.filter(function (x) { return x !== l; }); };
  }

  // ---------- Referenzen ----------
  function docRef(path) {
    var p = split(path), url = "/api/db/" + p.col + "/" + p.id;
    return {
      id: p.id, path: path,
      get: function () { return api("GET", url).then(function (d) { return docSnap(p.id, d); }, function (e) { if (e.code === "not_found") return docSnap(p.id, null); throw e; }); },
      set: function (data) { return api("PUT", url, data).then(function () {}); },
      update: function (data) { return api("PATCH", url, data).then(function () {}); },
      delete: function () { return api("DELETE", url).then(function () {}); },
      onSnapshot: function (next, error) { return subscribe({ kind: "doc", col: p.col, id: p.id, next: next, error: error }); }
    };
  }
  function colRef(col) {
    return {
      path: col,
      doc: function (id) { return id ? docRef(col + "/" + id) : docRef(col + "/" + Math.random().toString(36).slice(2, 14)); },
      add: function (data) { return api("POST", "/api/db/" + col, data).then(function (r) { return docRef(col + "/" + r.id); }); },
      get: function () { return api("GET", "/api/db/" + col).then(colSnap); },
      onSnapshot: function (next, error) { return subscribe({ kind: "col", col: col, id: undefined, next: next, error: error }); }
    };
  }

  var db = { doc: docRef, collection: colRef };
  var user = {
    isOwner: function () { return Promise.resolve(true); },
    canEdit: function () { return Promise.resolve(true); },
    can: function () { return Promise.resolve(true); },
    id: function () { return Promise.resolve("haushalt"); }
  };

  window.claude = {
    use: function (name) {
      if (name === "db") return Promise.resolve(db);
      if (name === "user") return Promise.resolve(user);
      return Promise.resolve(null);
    }
  };

  // Zusätzliche Server-Funktionen (Aktionen, Rezept-Import, Einstellungen).
  window.SB = {
    api: api,
    config: api("GET", "/api/config").catch(function () { return {}; })
  };
})();
