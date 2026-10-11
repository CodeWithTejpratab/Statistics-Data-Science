#!/usr/bin/env python3
"""
Aurora Media Group -- a synthetic media & entertainment SQLite database.

Models a fictional company with three business lines, the same shape as a
real media conglomerate:
  1. Streaming (Aurora+): titles, episodes, subscribers, plans, payments, viewing sessions, ratings
  2. Advertising: advertisers, campaigns, daily ad performance
  3. Linear TV: networks and airings with Nielsen-style ratings
  + marketing spend (for CAC), and a date dimension.

All data is synthetic (no real people or IP).

Usage:  python3 build_db.py
"""
import bisect
import datetime as dt
import os
import sqlite3
import time

import numpy as np

SEED = 42
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aurora_media.db")
START = dt.date(2022, 1, 1)
END = dt.date(2026, 9, 30)
N_USERS = 6000
N_TITLES = 240
ONE = dt.timedelta(days=1)

rng = np.random.default_rng(SEED)

SCHEMA = """
PRAGMA foreign_keys = OFF;

CREATE TABLE genres (
    genre_id INTEGER PRIMARY KEY,
    genre_name TEXT NOT NULL UNIQUE
);

CREATE TABLE titles (
    title_id INTEGER PRIMARY KEY,
    title_name TEXT NOT NULL,
    content_type TEXT NOT NULL CHECK (content_type IN ('movie','series')),
    genre_id INTEGER NOT NULL REFERENCES genres(genre_id),
    release_date TEXT NOT NULL,              -- date available on Aurora+
    maturity_rating TEXT,
    runtime_min INTEGER,                     -- movie runtime or typical episode runtime
    production_budget_usd INTEGER,
    is_original INTEGER NOT NULL CHECK (is_original IN (0,1)),
    critic_score INTEGER                     -- 0-100
);

CREATE TABLE episodes (
    episode_id INTEGER PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES titles(title_id),
    season_number INTEGER NOT NULL,
    episode_number INTEGER NOT NULL,
    episode_title TEXT,
    air_date TEXT NOT NULL,
    runtime_min INTEGER
);

CREATE TABLE people (
    person_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    primary_role TEXT NOT NULL CHECK (primary_role IN ('Actor','Director')),
    birth_year INTEGER
);

CREATE TABLE title_cast (
    title_id INTEGER NOT NULL REFERENCES titles(title_id),
    person_id INTEGER NOT NULL REFERENCES people(person_id),
    role_type TEXT NOT NULL,                 -- 'Lead','Supporting','Director'
    billing_order INTEGER,
    PRIMARY KEY (title_id, person_id)
);

CREATE TABLE plans (
    plan_id INTEGER PRIMARY KEY,
    plan_name TEXT NOT NULL,
    has_ads INTEGER NOT NULL,
    max_streams INTEGER NOT NULL
);

CREATE TABLE plan_price_history (
    plan_id INTEGER NOT NULL REFERENCES plans(plan_id),
    effective_date TEXT NOT NULL,
    monthly_price_usd REAL NOT NULL,
    PRIMARY KEY (plan_id, effective_date)
);

CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    signup_date TEXT NOT NULL,
    state TEXT,                              -- some NULLs on purpose
    region TEXT,
    age_band TEXT,                           -- some NULLs on purpose
    acquisition_channel TEXT NOT NULL,
    primary_device TEXT
);

CREATE TABLE subscriptions (
    subscription_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    plan_id INTEGER NOT NULL REFERENCES plans(plan_id),
    start_date TEXT NOT NULL,
    end_date TEXT,                           -- NULL = still active
    status TEXT NOT NULL CHECK (status IN ('active','ended')),
    end_reason TEXT                          -- cancellation reason, 'plan_change', 'payment_failed'
);

CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    payment_date TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success','failed'))
);

CREATE TABLE viewing_sessions (
    session_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    title_id INTEGER NOT NULL REFERENCES titles(title_id),
    episode_id INTEGER REFERENCES episodes(episode_id),   -- NULL for movies
    session_start TEXT NOT NULL,
    minutes_watched INTEGER NOT NULL,
    completed INTEGER NOT NULL,
    device_type TEXT,
    ads_shown INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE user_ratings (
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    title_id INTEGER NOT NULL REFERENCES titles(title_id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    rated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, title_id)
);

CREATE TABLE marketing_spend (
    month TEXT NOT NULL,                     -- 'YYYY-MM'
    channel TEXT NOT NULL,
    spend_usd REAL NOT NULL,
    PRIMARY KEY (month, channel)
);

CREATE TABLE advertisers (
    advertiser_id INTEGER PRIMARY KEY,
    advertiser_name TEXT NOT NULL,
    industry TEXT NOT NULL
);

CREATE TABLE ad_campaigns (
    campaign_id INTEGER PRIMARY KEY,
    advertiser_id INTEGER NOT NULL REFERENCES advertisers(advertiser_id),
    campaign_name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    budget_usd REAL NOT NULL,
    target_genre_id INTEGER REFERENCES genres(genre_id),  -- NULL = run of network
    objective TEXT
);

CREATE TABLE ad_daily_performance (
    perf_date TEXT NOT NULL,
    campaign_id INTEGER NOT NULL REFERENCES ad_campaigns(campaign_id),
    title_id INTEGER NOT NULL REFERENCES titles(title_id),
    impressions INTEGER NOT NULL,
    completed_views INTEGER NOT NULL,
    clicks INTEGER NOT NULL,
    revenue_usd REAL NOT NULL,
    PRIMARY KEY (perf_date, campaign_id, title_id)
);

CREATE TABLE networks (
    network_id INTEGER PRIMARY KEY,
    network_name TEXT NOT NULL,
    network_type TEXT NOT NULL
);

CREATE TABLE linear_airings (
    airing_id INTEGER PRIMARY KEY,
    network_id INTEGER NOT NULL REFERENCES networks(network_id),
    title_id INTEGER REFERENCES titles(title_id),         -- NULL for news, talk, live sports
    program_name TEXT NOT NULL,
    air_datetime TEXT NOT NULL,
    daypart TEXT NOT NULL,
    duration_min INTEGER NOT NULL,
    is_live INTEGER NOT NULL,
    household_rating REAL NOT NULL,
    viewers_thousands INTEGER NOT NULL,
    demo_18_49_rating REAL NOT NULL
);

CREATE TABLE dim_date (
    date TEXT PRIMARY KEY,
    year INTEGER, quarter INTEGER, month INTEGER, month_name TEXT,
    week_of_year INTEGER, day_of_week TEXT, is_weekend INTEGER
);
"""

INDEXES = """
CREATE INDEX idx_titles_genre        ON titles(genre_id);
CREATE INDEX idx_episodes_title      ON episodes(title_id);
CREATE INDEX idx_subs_user           ON subscriptions(user_id);
CREATE INDEX idx_subs_dates          ON subscriptions(start_date, end_date);
CREATE INDEX idx_pay_user            ON payments(user_id);
CREATE INDEX idx_pay_date            ON payments(payment_date);
CREATE INDEX idx_sess_user           ON viewing_sessions(user_id);
CREATE INDEX idx_sess_title          ON viewing_sessions(title_id);
CREATE INDEX idx_sess_start          ON viewing_sessions(session_start);
CREATE INDEX idx_ratings_title       ON user_ratings(title_id);
CREATE INDEX idx_adperf_campaign     ON ad_daily_performance(campaign_id);
CREATE INDEX idx_adperf_date         ON ad_daily_performance(perf_date);
CREATE INDEX idx_linear_net_date     ON linear_airings(network_id, air_datetime);
"""

VIEWS = """
CREATE VIEW v_monthly_revenue AS
SELECT substr(p.payment_date,1,7) AS month,
       pl.plan_name,
       COUNT(*)                   AS successful_payments,
       ROUND(SUM(p.amount_usd),2) AS revenue_usd
FROM payments p
JOIN subscriptions s ON s.subscription_id = p.subscription_id
JOIN plans pl        ON pl.plan_id = s.plan_id
WHERE p.status = 'success'
GROUP BY 1, 2;

CREATE VIEW v_title_engagement AS
SELECT t.title_id, t.title_name, t.content_type, g.genre_name, t.is_original,
       COUNT(*)                          AS sessions,
       COUNT(DISTINCT vs.user_id)        AS unique_viewers,
       ROUND(SUM(vs.minutes_watched)/60.0,1) AS hours_watched,
       ROUND(AVG(vs.completed),3)        AS completion_rate
FROM viewing_sessions vs
JOIN titles t ON t.title_id = vs.title_id
JOIN genres g ON g.genre_id = t.genre_id
GROUP BY t.title_id;

CREATE VIEW v_ad_campaign_summary AS
SELECT c.campaign_id, c.campaign_name, a.advertiser_name, a.industry,
       c.budget_usd,
       SUM(d.impressions)        AS impressions,
       SUM(d.clicks)             AS clicks,
       ROUND(SUM(d.revenue_usd),2) AS revenue_usd,
       ROUND(1.0*SUM(d.clicks)/SUM(d.impressions),5) AS ctr
FROM ad_campaigns c
JOIN advertisers a ON a.advertiser_id = c.advertiser_id
JOIN ad_daily_performance d ON d.campaign_id = c.campaign_id
GROUP BY c.campaign_id;
"""


def add_months(d, n):
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, d.day)


def pick(options, p=None):
    return options[int(rng.choice(len(options), p=p))]


def build_catalog():
    genres = ["Drama", "Comedy", "Action", "Thriller", "Sci-Fi", "Horror", "Reality",
              "Documentary", "Animation", "Crime", "Romance", "Sports", "Kids"]
    gw = np.array([14, 14, 10, 9, 7, 6, 9, 6, 6, 8, 5, 3, 3], float)
    gw /= gw.sum()

    adj = ["Midnight", "Silver", "Hollow", "Crimson", "Quiet", "Broken", "Golden", "Last", "Electric",
           "Paper", "Velvet", "Iron", "Distant", "Neon", "Wild", "Silent", "Burning", "Hidden",
           "Northern", "Lucky", "Glass", "Savage", "Gentle", "Rusted", "Bright", "Fallen", "Hungry",
           "Lonely", "Marble", "Ocean", "Pale", "Restless", "Scarlet", "Stormy", "Thin", "Winter",
           "Young", "Cold", "Double", "Sacred"]
    noun = ["Harbor", "Empire", "Garden", "Signal", "Orchard", "Kingdom", "Echo", "Frontier", "Highway",
            "Lantern", "Mirror", "Station", "Tide", "Citadel", "Carnival", "Archive", "Compass",
            "District", "Engine", "Fortune", "Game", "House", "Island", "Jury", "Key", "Letters",
            "Market", "Nation", "Oracle", "Parade", "Quarry", "River", "Season", "Theory", "Union",
            "Valley", "Witness", "Yard", "Zone", "Bridge"]
    studios = ["Aurora Studios", "Aurora Originals", "Harbor Lane Pictures", "Northlight Films",
               "Bluebird Television", "Meridian Entertainment", "Copperfield Productions"]

    names, used = [], set()
    while len(names) < N_TITLES:
        a, n, n2 = pick(adj), pick(noun), pick(noun)
        pat = int(rng.integers(0, 4))
        nm = [f"{a} {n}", f"The {a} {n}", f"{n} of {n2}", f"{a} {n} Club"][pat]
        if nm not in used:
            used.add(nm)
            names.append(nm)

    titles, episodes = [], []
    ep_id = 0
    eps_by_title = {}
    for tid in range(1, N_TITLES + 1):
        g_idx = int(rng.choice(len(genres), p=gw))
        gname = genres[g_idx]
        ctype = "series" if (gname == "Reality" or rng.random() < 0.6) else "movie"
        is_orig = int(rng.random() < 0.38)
        # licensed library skews older; originals are premiering on-platform
        if is_orig or rng.random() < 0.35:
            rd = START + dt.timedelta(days=int(rng.integers(0, (dt.date(2026, 8, 15) - START).days)))
        else:
            rd = dt.date(2012, 1, 1) + dt.timedelta(days=int(rng.integers(0, 3650)))
        pop = float(rng.lognormal(0, 0.9)) * (1.5 if is_orig else 1.0)
        critic = int(np.clip(58 + 11 * np.log(pop) + rng.normal(0, 9), 18, 98))
        if ctype == "movie":
            runtime = int(rng.integers(85, 150))
            rating = pick(["PG", "PG-13", "R"], [0.2, 0.45, 0.35])
        else:
            runtime = int(rng.integers(21, 28)) if gname in ("Comedy", "Animation", "Kids") else int(rng.integers(40, 60))
            rating = pick(["TV-PG", "TV-14", "TV-MA"], [0.2, 0.5, 0.3])
        if gname == "Kids":
            rating = "TV-Y7" if ctype == "series" else "G"
        elif gname in ("Horror", "Crime") and rating in ("PG", "TV-PG"):
            rating = "R" if ctype == "movie" else "TV-MA"
        budget = int(rng.lognormal(17.2, 0.8))
        titles.append((tid, names[tid - 1], ctype, g_idx + 1, rd.isoformat(), rating, runtime, budget,
                       is_orig, critic, pop, gname))

        if ctype == "series":
            n_seasons = int(pick([1, 2, 3, 4], [0.4, 0.3, 0.2, 0.1]))
            lst = []
            for s in range(1, n_seasons + 1):
                premiere = rd + dt.timedelta(days=365 * (s - 1) + int(rng.integers(-20, 20)))
                if s == 1:
                    premiere = rd
                n_eps = int(rng.integers(6, 13))
                for e in range(1, n_eps + 1):
                    # originals release weekly; licensed seasons drop all at once
                    air = premiere + dt.timedelta(days=7 * (e - 1)) if is_orig else premiere
                    if air > END:
                        continue
                    ep_id += 1
                    episodes.append((ep_id, tid, s, e, f"Episode {e}", air.isoformat(), runtime))
                    lst.append((ep_id, air.toordinal(), runtime))
            eps_by_title[tid] = lst
    return genres, titles, episodes, eps_by_title, studios


def main():
    t0 = time.time()
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)

    # ---------------- catalog ----------------
    genres, titles, episodes, eps_by_title, _ = build_catalog()
    con.executemany("INSERT INTO genres VALUES (?,?)", [(i + 1, g) for i, g in enumerate(genres)])
    con.executemany("INSERT INTO titles VALUES (?,?,?,?,?,?,?,?,?,?)", [t[:10] for t in titles])
    con.executemany("INSERT INTO episodes VALUES (?,?,?,?,?,?,?)", episodes)
    T = len(titles)
    pop = np.array([t[10] for t in titles])
    is_orig = np.array([t[8] for t in titles])
    genre_idx = np.array([t[3] - 1 for t in titles])
    release_ord = np.array([dt.date.fromisoformat(t[4]).toordinal() for t in titles])
    t_runtime = [t[6] for t in titles]
    t_type = [t[2] for t in titles]

    # people & cast
    first = ["Ava", "Liam", "Noah", "Mia", "Zoe", "Ethan", "Lena", "Omar", "Priya", "Marcus", "Sofia", "Diego",
             "Hana", "Tariq", "Elena", "Jonah", "Nia", "Felix", "Ruth", "Andre", "Maya", "Kofi", "Iris", "Leo",
             "Camila", "Dev", "June", "Rafael", "Tess", "Amir", "Lucia", "Wes", "Nora", "Jamal", "Yuki", "Theo",
             "Ines", "Caleb", "Anya", "Miles"]
    last = ["Alvarez", "Brooks", "Chen", "Dubois", "Evans", "Fischer", "Gupta", "Haddad", "Ito", "Jensen",
            "Kim", "Lopez", "Moreau", "Nakamura", "Okafor", "Patel", "Quinn", "Rossi", "Silva", "Turner",
            "Usman", "Vega", "Walker", "Xu", "Young", "Zhang", "Adler", "Baker", "Castillo", "Diaz",
            "Ellis", "Foster", "Grant", "Hughes", "Ivanov", "Jordan", "Klein", "Lowe", "Murphy", "Novak"]
    seen, people = set(), []
    while len(people) < 400:
        nm = f"{pick(first)} {pick(last)}"
        if nm in seen:
            continue
        seen.add(nm)
        pid = len(people) + 1
        role = "Director" if pid <= 70 else "Actor"
        people.append((pid, nm, role, int(rng.integers(1950, 2003))))
    con.executemany("INSERT INTO people VALUES (?,?,?,?)", people)
    dirs = np.arange(1, 71)
    actors = np.arange(71, 401)
    aw = 1.0 / np.arange(1, len(actors) + 1) ** 0.7
    aw /= aw.sum()
    cast = []
    for t in titles:
        cast.append((t[0], int(rng.choice(dirs)), "Director", 0))
        chosen = rng.choice(actors, size=int(rng.integers(4, 7)), replace=False, p=aw)
        for i, a in enumerate(chosen):
            cast.append((t[0], int(a), "Lead" if i < 2 else "Supporting", i + 1))
    con.executemany("INSERT INTO title_cast VALUES (?,?,?,?)", cast)

    # ---------------- plans & prices ----------------
    con.executemany("INSERT INTO plans VALUES (?,?,?,?)",
                    [(1, "Basic with Ads", 1, 1), (2, "Premium", 0, 2), (3, "Premium Plus", 0, 4)])
    price_hist = [(1, "2022-01-01", 6.99), (1, "2024-07-01", 7.99),
                  (2, "2022-01-01", 11.99), (2, "2024-07-01", 13.99),
                  (3, "2022-01-01", 17.99), (3, "2025-06-01", 19.99)]
    con.executemany("INSERT INTO plan_price_history VALUES (?,?,?)", price_hist)
    bumps = {1: dt.date(2024, 7, 1), 2: dt.date(2024, 7, 1), 3: dt.date(2025, 6, 1)}

    def price_at(plan, d):
        best = None
        for p, eff, price in price_hist:
            if p == plan and dt.date.fromisoformat(eff) <= d:
                best = price
        return best

    # ---------------- users ----------------
    states = {"Northeast": ["NY", "NJ", "MA", "PA", "CT"], "Southeast": ["FL", "GA", "NC", "VA", "TN"],
              "Midwest": ["IL", "OH", "MI", "MN", "WI"], "Southwest": ["TX", "AZ", "OK", "NM"],
              "West": ["CA", "WA", "OR", "CO", "NV"]}
    state_list = [(s, r) for r, ss in states.items() for s in ss]
    sw = np.array([3.0 if s in ("NY", "CA", "TX", "FL") else 1.0 for s, _ in state_list])
    sw /= sw.sum()
    channels = ["organic", "paid_social", "paid_search", "bundle_partner", "referral", "email"]
    cw = [0.30, 0.22, 0.15, 0.17, 0.09, 0.07]
    devices = ["Smart TV", "Mobile", "Web", "Tablet", "Streaming Stick", "Game Console"]
    dw = [0.34, 0.2, 0.1, 0.06, 0.25, 0.05]
    ages = ["18-24", "25-34", "35-44", "45-54", "55+"]
    aw_ = [0.2, 0.32, 0.22, 0.14, 0.12]

    days = [START + dt.timedelta(days=i) for i in range((END - START).days + 1)]
    sw_days = 1 + 0.9 * np.arange(len(days)) / len(days)
    # premiere spikes: big originals pull in signups
    big = sorted([t for t in titles if t[8] == 1 and dt.date.fromisoformat(t[4]) <= END],
                 key=lambda x: -x[10])[:14]
    for t in big:
        rd = dt.date.fromisoformat(t[4])
        for i, d in enumerate(days):
            if d >= rd:
                sw_days[i] += 7 * np.exp(-(d - rd).days / 9.0)
    sw_days /= sw_days.sum()

    users, user_meta = [], {}
    signup_idx = rng.choice(len(days), size=N_USERS, p=sw_days)
    for u in range(1, N_USERS + 1):
        d = days[int(signup_idx[u - 1])]
        if d.day > 28:
            d = d.replace(day=28)
        st, rg = state_list[int(rng.choice(len(state_list), p=sw))]
        if rng.random() < 0.015:
            st = rg = None
        age = None if rng.random() < 0.04 else pick(ages, aw_)
        ch = pick(channels, cw)
        dev = pick(devices, dw)
        users.append((u, d.isoformat(), st, rg, age, ch, dev))
        user_meta[u] = (d, ch, dev)
    con.executemany("INSERT INTO users VALUES (?,?,?,?,?,?,?)", users)

    # ---------------- monthly title weights ----------------
    month_w = {}
    cur = dt.date(START.year, START.month, 1)
    while cur <= END:
        mid = cur.replace(day=15).toordinal()
        age = mid - release_ord
        boost = np.where(is_orig == 1, 1 + 4.0 * np.exp(-np.maximum(age, 0) / 45.0),
                         1 + 1.2 * np.exp(-np.maximum(age, 0) / 45.0))
        # older library content decays a little
        decay = np.where(age > 1500, 0.65, 1.0)
        w = np.where(age >= -15, pop * boost * decay, 0.0)
        month_w[cur.year * 12 + cur.month] = w
        cur = add_months(cur, 1)

    # ---------------- subscriptions, payments, sessions, ratings ----------------
    subs, pays, sessions, ratings = [], [], [], []
    sub_id = pay_id = sess_id = 0
    prog = {}
    rated = set()
    hour_w = np.array([1, .5, .3, .2, .2, .3, .6, 1, 1, 1, 1, 1.2, 1.5, 1.5, 1.5, 1.7, 2, 2.5, 3.5, 5, 6.5, 6.5, 4.5, 2.5])
    hour_w /= hour_w.sum()
    ch_churn = {"organic": 1.0, "paid_social": 1.3, "paid_search": 1.1, "bundle_partner": 0.6,
                "referral": 0.8, "email": 0.9}
    plan_churn = {1: 1.2, 2: 1.0, 3: 0.85}
    reasons = ["too_expensive", "not_enough_content", "switched_service", "temporary_pause", "other"]
    reason_p = [0.32, 0.22, 0.2, 0.16, 0.10]
    season = {1: 1.12, 2: 1.05, 3: 1.0, 4: 0.97, 5: 0.93, 6: 0.88, 7: 0.9, 8: 0.92, 9: 0.98, 10: 1.02, 11: 1.08, 12: 1.15}
    plan_trans = {1: ([2, 3], [0.7, 0.3]), 2: ([1, 3], [0.5, 0.5]), 3: ([2, 1], [0.8, 0.2])}

    sess_cols = "(session_id,user_id,title_id,episode_id,session_start,minutes_watched,completed,device_type,ads_shown)"

    def flush_sessions():
        if sessions:
            con.executemany(f"INSERT INTO viewing_sessions {sess_cols} VALUES (?,?,?,?,?,?,?,?,?)", sessions)
            sessions.clear()

    for u in range(1, N_USERS + 1):
        signup, ch, dev = user_meta[u]
        eng = float(rng.lognormal(0, 0.5))
        userpref = rng.dirichlet(np.ones(len(genres)) * 0.7) * len(genres) + 0.15
        plan = pick([1, 2, 3], [0.5, 0.35, 0.15])
        d = signup
        sub_id += 1
        cur_sub, sub_start, tenure = sub_id, d, 0
        periods = []
        while True:
            pe = add_months(d, 1) - ONE
            price = price_at(plan, d)
            pay_id += 1
            pays.append((pay_id, cur_sub, u, d.isoformat(), price, "success"))
            periods.append((d, pe, plan))
            tenure += 1
            nxt = pe + ONE
            if nxt > END:
                subs.append((cur_sub, u, plan, sub_start.isoformat(), None, "active", None))
                break
            base = {1: 0.10, 2: 0.08, 3: 0.06}.get(tenure, 0.035)
            p = base * ch_churn[ch] * plan_churn[plan] * float(np.exp(-0.45 * (eng - 1)))
            if bumps[plan] <= nxt <= bumps[plan] + dt.timedelta(days=75):
                p += 0.02
            p = min(p, 0.5)
            r = rng.random()
            if r < p:
                reason = pick(reasons, reason_p)
                if rng.random() < 0.12:
                    reason = "payment_failed"
                    pay_id += 1
                    pays.append((pay_id, cur_sub, u, nxt.isoformat(), price_at(plan, nxt), "failed"))
                subs.append((cur_sub, u, plan, sub_start.isoformat(), pe.isoformat(), "ended", reason))
                if rng.random() < 0.18:
                    d2 = add_months(nxt, int(rng.integers(2, 11)))
                    if d2 > END:
                        break
                    d = d2
                    sub_id += 1
                    cur_sub, sub_start, tenure = sub_id, d, 0
                    continue
                break
            elif r < p + 0.012:
                subs.append((cur_sub, u, plan, sub_start.isoformat(), pe.isoformat(), "ended", "plan_change"))
                opts, pr = plan_trans[plan]
                plan = pick(opts, pr)
                sub_id += 1
                cur_sub, sub_start = sub_id, nxt
                d = nxt
            else:
                d = nxt

        # ---- sessions for every paid period ----
        for (ps, pe, pl) in periods:
            hi = min(pe, END)
            n_days = (hi - ps).days + 1
            if n_days <= 0:
                continue
            full_days = (pe - ps).days + 1
            lam = (1.2 + 2.5 * eng) * season[ps.month] * (n_days / full_days)
            n = int(rng.poisson(lam))
            if n == 0:
                continue
            w = month_w[ps.year * 12 + ps.month] * userpref[genre_idx]
            if w.sum() <= 0:
                continue
            w = w / w.sum()
            tids = rng.choice(T, size=n, p=w)
            dws = np.array([1.4 if (ps + dt.timedelta(days=i)).weekday() >= 5 else 1.0 for i in range(n_days)])
            doffs = rng.choice(n_days, size=n, p=dws / dws.sum())
            hrs = rng.choice(24, size=n, p=hour_w)
            for ti, off, hr in zip(tids, doffs, hrs):
                ti = int(ti)
                day = max(ps + dt.timedelta(days=int(off)), dt.date.fromordinal(int(release_ord[ti])))
                if day > hi:
                    continue
                start = dt.datetime.combine(day, dt.time(int(hr), int(rng.integers(0, 60))))
                tid = ti + 1
                device = dev if rng.random() < 0.65 else pick(devices, dw)
                has_ads = 1 if pl == 1 else 0
                if t_type[ti] == "movie":
                    chain = [(None, t_runtime[ti])]
                else:
                    lst = eps_by_title[tid]
                    aired = bisect.bisect_right([x[1] for x in lst], day.toordinal())
                    if aired == 0:
                        continue
                    pg = prog.get((u, tid), 0)
                    if pg >= aired or rng.random() < 0.15:
                        idx = int(rng.integers(0, aired))
                    else:
                        idx = pg
                        prog[(u, tid)] = pg + 1
                    extras = int(pick([0, 1, 2, 3], [0.55, 0.25, 0.12, 0.08]))
                    chain = []
                    for k in range(extras + 1):
                        if idx + k < aired:
                            chain.append((lst[idx + k][0], lst[idx + k][2]))
                    if chain and idx + len(chain) > prog.get((u, tid), 0):
                        prog[(u, tid)] = max(prog.get((u, tid), 0), idx + len(chain))
                for ep, rt in chain:
                    if start.date() > END:
                        break
                    comp_p = 0.58 if ep is None else 0.72
                    done = rng.random() < comp_p
                    mins = int(rt * rng.uniform(0.97, 1.0)) if done else max(1, int(rt * rng.uniform(0.05, 0.9)))
                    ads = int(rng.poisson(mins / 8.0)) if has_ads else 0
                    sess_id += 1
                    sessions.append((sess_id, u, tid, ep, start.strftime("%Y-%m-%d %H:%M:%S"),
                                     mins, int(done), device, ads))
                    if done and (u, tid) not in rated and rng.random() < 0.07:
                        rated.add((u, tid))
                        crit = titles[ti][9]
                        rv = int(np.clip(round(crit / 20 + rng.normal(0, 0.9)), 1, 5))
                        ratings.append((u, tid, rv, start.strftime("%Y-%m-%d")))
                    start = start + dt.timedelta(minutes=mins + 1)
        if len(sessions) > 60000:
            flush_sessions()

    flush_sessions()
    con.executemany("INSERT INTO subscriptions VALUES (?,?,?,?,?,?,?)", subs)
    con.executemany("INSERT INTO payments VALUES (?,?,?,?,?,?)", pays)
    con.executemany("INSERT INTO user_ratings VALUES (?,?,?,?)", ratings)

    # ---------------- marketing spend (CAC) ----------------
    cac = {"organic": 4, "paid_social": 38, "paid_search": 45, "bundle_partner": 18, "referral": 12, "email": 6}
    counts = {}
    for u in users:
        k = (u[1][:7], u[5])
        counts[k] = counts.get(k, 0) + 1
    cur = dt.date(START.year, START.month, 1)
    mrows = []
    while cur <= END:
        m = cur.strftime("%Y-%m")
        for c in channels:
            n = counts.get((m, c), 0)
            mrows.append((m, c, round(max(n, 1) * cac[c] * float(rng.lognormal(0, 0.15)), 2)))
        cur = add_months(cur, 1)
    con.executemany("INSERT INTO marketing_spend VALUES (?,?,?)", mrows)

    # ---------------- advertising ----------------
    industries = ["Auto", "CPG", "Retail", "Telecom", "Finance", "QSR", "Pharma", "Travel", "Tech", "Entertainment"]
    cpm_base = {"Auto": 32, "CPG": 22, "Retail": 24, "Telecom": 26, "Finance": 34, "QSR": 20,
                "Pharma": 36, "Travel": 28, "Tech": 30, "Entertainment": 25}
    brand_a = ["Northwind", "Summit", "Evergreen", "Pioneer", "Blue Harbor", "Redwood", "Atlas", "Zenith",
               "Cascade", "Ironclad", "Maple", "Orbit", "Sterling", "Vista", "Willow", "Apex", "Beacon", "Crest"]
    brand_b = ["Motors", "Foods", "Bank", "Mobile", "Air", "Pharma", "Retail", "Labs", "Burgers", "Travel"]
    advs, used = [], set()
    while len(advs) < 60:
        nm = f"{pick(brand_a)} {pick(brand_b)}"
        if nm in used:
            continue
        used.add(nm)
        ind = {"Motors": "Auto", "Foods": "CPG", "Bank": "Finance", "Mobile": "Telecom", "Air": "Travel",
               "Pharma": "Pharma", "Retail": "Retail", "Labs": "Tech", "Burgers": "QSR", "Travel": "Travel"}[nm.split()[-1]]
        advs.append((len(advs) + 1, nm, ind))
    con.executemany("INSERT INTO advertisers VALUES (?,?,?)", advs)
    adv_ind = {a[0]: a[2] for a in advs}
    objectives = ["Awareness", "Consideration", "Conversion"]
    camps, perf = [], []
    for cid in range(1, 221):
        aid = int(rng.integers(1, 61))
        s = dt.date(2022, 6, 1) + dt.timedelta(days=int(rng.integers(0, (dt.date(2026, 8, 15) - dt.date(2022, 6, 1)).days)))
        e = min(s + dt.timedelta(days=int(rng.integers(14, 91))), END)
        budget = round(float(rng.lognormal(12.3, 0.9)), 2)
        tg = int(rng.integers(1, len(genres) + 1)) if rng.random() < 0.55 else None
        camps.append((cid, aid, f"{advs[aid - 1][1]} {pick(['Spring','Summer','Fall','Holiday','Launch','Always-On'])} {s.year}",
                      s.isoformat(), e.isoformat(), budget, tg, pick(objectives, [0.45, 0.3, 0.25])))
        ndays = (e - s).days + 1
        cpm = cpm_base[adv_ind[aid]]
        for i in range(ndays):
            d = s + dt.timedelta(days=i)
            w = month_w[d.year * 12 + d.month].copy()
            if tg:
                w = np.where(genre_idx == tg - 1, w * 4, w)
            if w.sum() <= 0:
                continue
            w = w / w.sum()
            picks_ = rng.choice(T, size=3, replace=False, p=w)
            for ti in picks_:
                imp = int(budget / ndays / 3 / cpm * 1000 * rng.lognormal(0, 0.25))
                comp = int(imp * rng.uniform(0.6, 0.95))
                clk = int(imp * rng.uniform(0.001, 0.012))
                prem = 1.25 if is_orig[int(ti)] else 1.0
                perf.append((d.isoformat(), cid, int(ti) + 1, imp, comp, clk, round(imp * cpm * prem / 1000, 2)))
    con.executemany("INSERT INTO ad_campaigns VALUES (?,?,?,?,?,?,?,?)", camps)
    con.executemany("INSERT INTO ad_daily_performance VALUES (?,?,?,?,?,?,?)", perf)

    # ---------------- linear TV ----------------
    nets = [(1, "Aurora Broadcast", "Broadcast"), (2, "Aurora Entertainment", "Cable Entertainment"),
            (3, "Aurora News Now", "Cable News"), (4, "Aurora Sports Network", "Cable Sports"),
            (5, "Aurora Kids", "Kids"), (6, "Aurora Latino", "Spanish-language")]
    con.executemany("INSERT INTO networks VALUES (?,?,?)", nets)
    net_mult = {1: 1.0, 2: 0.55, 3: 0.7, 4: 0.9, 5: 0.35, 6: 0.3}
    dayparts = [("Morning", 7, 60, 1.8), ("Daytime", 13, 60, 1.4), ("Early Fringe", 18, 60, 2.4),
                ("Prime", 20, 120, 3.5), ("Late Night", 23, 60, 1.6), ("Overnight", 2, 60, 0.5)]
    prog_names = {
        1: ["Aurora Today", "Daytime Live", "Aurora Evening News", None, "Late Night Show", "Overnight Replay"],
        2: ["Morning Reruns", "Afternoon Marathon", "Reality Block", None, "Late Reruns", "Overnight Replay"],
        3: ["News Now Morning", "News Now Midday", "News Now Evening", "News Now Prime", "News Now Tonight", "News Now Overnight"],
        4: ["Sports Morning", "Classic Games", "Sports Desk", "Live Game Night", "Highlights Tonight", "Replay Overnight"],
        5: ["Kids Morning Block", "Kids Afternoon Block", "Kids After School", "Kids Family Movie", "Family Classics", "Kids Overnight"],
        6: ["Buenos Dias", "Tarde de Novelas", "Noticiero Vespertino", "Novela Estelar", "Noticiero Nocturno", "Replay"],
    }
    series_ids = [t[0] for t in titles if t[2] == "series"]
    movie_ids = [t[0] for t in titles if t[2] == "movie"]
    title_names = {t[0]: t[1] for t in titles}
    lrows, aid_ = [], 0
    for d in days:
        yrs = (d - START).days / 365.0
        sea = 0.85 if d.month in (6, 7, 8) else (1.08 if d.month in (11, 12, 1, 2) else 1.0)
        wk = 1.0
        for (nid, nname, ntype) in nets:
            for di, (dp, hr, dur, base) in enumerate(dayparts):
                live = 1 if (ntype in ("Cable News", "Cable Sports") or (ntype == "Broadcast" and dp == "Early Fringe")) else 0
                tid = None
                pname = prog_names[nid][di]
                if pname is None:
                    pool = series_ids if (nid == 1 or d.weekday() < 5) else movie_ids
                    tid = int(rng.choice(pool))
                    pname = title_names[tid]
                bump = 1.0
                if ntype == "Cable Sports" and dp == "Prime":
                    bump = 2.2 if d.weekday() in (5, 6) else 0.9
                if ntype == "Cable News" and dp == "Early Fringe":
                    bump = 1.5
                if ntype == "Broadcast" and dp == "Prime" and d.weekday() == 6:
                    bump = 1.25
                hh = base * net_mult[nid] * bump * sea * (1 - 0.08 * yrs) * float(rng.lognormal(0, 0.12))
                hh = round(max(hh, 0.05), 2)
                aid_ += 1
                lrows.append((aid_, nid, tid, pname,
                              dt.datetime.combine(d, dt.time(hr, 0)).strftime("%Y-%m-%d %H:%M:%S"),
                              dp, dur, live, hh, int(hh * 1100 * rng.uniform(0.95, 1.05)),
                              round(hh * rng.uniform(0.3, 0.45), 2)))
    con.executemany("INSERT INTO linear_airings VALUES (?,?,?,?,?,?,?,?,?,?,?)", lrows)

    # ---------------- dim_date ----------------
    drows = []
    for d in days:
        drows.append((d.isoformat(), d.year, (d.month - 1) // 3 + 1, d.month, d.strftime("%B"),
                      int(d.strftime("%W")), d.strftime("%A"), int(d.weekday() >= 5)))
    con.executemany("INSERT INTO dim_date VALUES (?,?,?,?,?,?,?,?)", drows)

    con.executescript(INDEXES)
    con.executescript(VIEWS)
    con.commit()
    con.execute("ANALYZE")
    con.commit()

    print(f"Built {DB} in {time.time() - t0:.0f}s ({os.path.getsize(DB) / 1e6:.0f} MB)")
    for (tbl,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:<22}{n:>10,}")
    con.close()


if __name__ == "__main__":
    main()
