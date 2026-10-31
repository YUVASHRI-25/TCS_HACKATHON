"""Generate TRACE-DEMO: a seeded SYNTHETIC dataset in the SIFTLINE schema, for demos.

    python scripts/generate_demo_dataset.py [--out data/raw/TRACE_DEMO] [--seed 7]

This is an INPUT dataset, not app data: TRACE reads it through config/mapping.yaml (or the dataset upload
screen) and computes every threshold, finding, case and score from it like any other dataset.

Background behaviour is generated to look like ordinary retail/business banking (habitual counterparties,
one home currency per customer, heavy-tailed amounts, daytime activity) so that percentile thresholds
mean something. On top of it a few scenarios are planted, plus legitimate look-alikes that should be
explained away or stay below the two-finding-type case rule. Planted ring members are written to
suspicious_ring_members.csv, which TRACE maps to LabelledMember and uses for reporting only.
Everything here is fictional: names are "Demo Customer NNNNN", IPs are private-range addresses.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

START = datetime(2025, 10, 1)
END = datetime(2026, 9, 30, 23, 59)
CURRENCIES = {"USD": 1.0, "GBP": 0.79, "INR": 83.0, "SGD": 1.35, "AED": 3.67}
HOME_P = [0.5, 0.15, 0.15, 0.1, 0.1]
NATION = {"USD": "US", "GBP": "GB", "INR": "IN", "SGD": "SG", "AED": "AE"}
HOURS_P = np.array([1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8, 8, 8, 8, 8, 8, 8, 7, 7, 6, 5, 4, 3, 2], float)
HOURS_P /= HOURS_P.sum()
SYLL = ["ka", "ri", "mo", "ten", "sa", "vel", "dor", "an", "lu", "zor", "pe", "qui", "ba", "ny", "ost", "ira",
        "fen", "go", "hal", "ju", "mer", "ul", "wex", "tia", "bro", "cal", "eld", "vin", "sho", "rak"]
BUSINESS_SUFFIX = ["Trading", "Holdings", "Logistics", "Ventures", "Supplies", "Imports", "Services", "Partners"]


class Builder:
    def __init__(self, seed: int):
        self.r = np.random.default_rng(seed)
        self.tables: dict[str, list[dict]] = {k: [] for k in (
            "customers", "accounts", "devices", "shared_devices", "ip_addresses", "logins", "merchants",
            "beneficiaries", "entity_relationships", "complaints", "alerts", "investigation_cases",
            "watchlist_matches", "suspicious_ring_members")}
        self.txns: list[dict] = []
        self.cust_cur: dict[str, str] = {}
        self.cust_accounts: dict[str, list[str]] = {}
        self.acct_cur: dict[str, str] = {}
        self.acct_cust: dict[str, str] = {}
        self.cust_device: dict[str, str] = {}
        self.cust_ip: dict[str, str] = {}
        self.scenarios: dict[str, dict] = {}
        self.names_seen: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ ids and primitives
    def _id(self, table: str, prefix: str, width: int) -> str:
        return f"{prefix}{len(self.tables[table]) + 1:0{width}d}"

    def rand_ts(self, lo: datetime = START, hi: datetime = END) -> datetime:
        day = lo + timedelta(days=int(self.r.integers(0, max(1, (hi - lo).days))))
        return day.replace(hour=int(self.r.choice(24, p=HOURS_P)), minute=int(self.r.integers(0, 60)))

    def name(self, business: bool) -> str:
        """Invented, clearly fictional names, kept dissimilar from each other so that entity resolution
        only fires where a scenario plants a near-duplicate."""
        while True:
            parts = [("".join(self.r.choice(SYLL, size=int(self.r.integers(2, 4))))).capitalize() for _ in range(2)]
            n = f"{parts[0]} {self.r.choice(BUSINESS_SUFFIX)}" if business else " ".join(parts)
            key = " ".join(sorted(n.lower().split()))
            if all(SequenceMatcher(None, key, k).ratio() < 0.8 for k in self.names_seen.get(key[0], [])):
                self.names_seen.setdefault(key[0], []).append(key)
                return n

    def customer(self, cur: str, *, business: bool = False, occupation: str | None = None,
                 risk: str | None = None, kyc: str | None = None) -> str:
        cid = self._id("customers", "C", 5)
        dob = datetime(1950, 1, 1) + timedelta(days=int(self.r.integers(0, 365 * 52)))
        self.tables["customers"].append({
            "customer_id": cid, "name": self.name(business),
            "date_of_birth": dob.date().isoformat(),
            "nationality": NATION[cur] if self.r.random() < 0.85 else self.r.choice(list(NATION.values())),
            "occupation": occupation or ("Business Owner" if business else
                                         self.r.choice(["Analyst", "Engineer", "Teacher", "Trader", "Nurse",
                                                        "Driver", "Student", "Retired"])),
            "risk_rating": risk or self.r.choice(["LOW", "MEDIUM", "HIGH"], p=[0.7, 0.25, 0.05]),
            "kyc_status": kyc or self.r.choice(["VERIFIED", "PENDING", "EXPIRED"], p=[0.9, 0.06, 0.04])})
        self.cust_cur[cid] = cur
        self.cust_accounts[cid] = []
        return cid

    def account(self, cid: str, atype: str, status: str = "ACTIVE") -> str:
        aid = self._id("accounts", "A", 6)
        bank = int(self.r.integers(1, 6))
        self.tables["accounts"].append({
            "account_id": aid, "customer_id": cid, "bank_id": f"B{bank:03d}",
            "branch_id": f"BR{(bank - 1) * 6 + int(self.r.integers(1, 7)):03d}", "account_type": atype,
            "status": status})
        self.cust_accounts[cid].append(aid)
        self.acct_cur[aid] = self.cust_cur[cid]
        self.acct_cust[aid] = cid
        return aid

    def device(self, dtype: str | None = None) -> str:
        did = self._id("devices", "D", 5)
        dtype = dtype or self.r.choice(["MOBILE", "DESKTOP", "TABLET"], p=[0.7, 0.2, 0.1])
        os_ = {"MOBILE": ["Android", "iOS"], "TABLET": ["Android", "iOS"], "DESKTOP": ["Windows", "macOS"]}[dtype]
        self.tables["devices"].append({
            "device_id": did, "fingerprint": "FP" + self.r.bytes(6).hex().upper(), "device_type": dtype,
            "operating_system": self.r.choice(os_), "browser": self.r.choice(["Chrome", "Safari", "Edge", "Firefox"])})
        return did

    def use_device(self, did: str, cid: str, first: datetime, last: datetime) -> None:
        self.tables["shared_devices"].append({
            "shared_device_record_id": self._id("shared_devices", "SH", 5), "device_id": did, "customer_id": cid,
            "first_seen": first.date().isoformat(), "last_seen": max(first, last).date().isoformat()})

    def ip(self, network_type: str, country: str) -> str:
        iid = self._id("ip_addresses", "IP", 5)
        n = len(self.tables["ip_addresses"]) + 1
        self.tables["ip_addresses"].append({
            "ip_id": iid, "ip_address": f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}",
            "isp": self.r.choice(["ExampleNet", "Global Fiber", "Metro ISP"]), "country": country,
            "network_type": network_type})
        return iid

    def login(self, cid: str, did: str, iid: str, ts: datetime) -> None:
        self.tables["logins"].append({
            "login_id": self._id("logins", "L", 6), "customer_id": cid, "device_id": did, "ip_id": iid,
            "timestamp": ts, "status": self.r.choice(["SUCCESS", "MFA_REQUIRED", "FAILED"], p=[0.88, 0.09, 0.03])})

    def txn(self, src: str, dst: str, amount: float, ts: datetime, ttype: str = "TRANSFER",
            channel: str | None = None, status: str = "COMPLETED", cur: str | None = None) -> None:
        self.txns.append({
            "sender_account_id": src, "receiver_account_id": dst, "amount": round(float(amount), 2),
            "currency": cur or self.acct_cur[src], "timestamp": ts, "transaction_type": ttype,
            "channel": channel or self.r.choice(["MOBILE", "WEB", "API", "BRANCH", "ATM"],
                                                p=[0.55, 0.3, 0.08, 0.05, 0.02]),
            "status": status})

    def relate(self, a: str, b: str, rtype: str, source: str = "DECLARATION") -> None:
        self.tables["entity_relationships"].append({
            "relationship_id": self._id("entity_relationships", "REL", 5), "entity_1_id": a, "entity_2_id": b,
            "relationship_type": rtype, "source": source})

    def complaint(self, cid: str, ctype: str, ts: datetime, status: str | None = None) -> None:
        self.tables["complaints"].append({
            "complaint_id": self._id("complaints", "COMP", 5), "customer_id": cid, "complaint_type": ctype,
            "timestamp": ts, "status": status or self.r.choice(["OPEN", "RESOLVED", "REFERRED"], p=[0.2, 0.7, 0.1])})

    def label(self, entity: str, role: str, typology: str) -> None:
        self.tables["suspicious_ring_members"].append({
            "ring_id": self._id("suspicious_ring_members", "RING", 4), "member_entity_id": entity, "role": role,
            "typology": typology})

    def online_identity(self, cid: str, *, extra_ips: list[str] = (), extra_devices: list[str] = (),
                        n_logins: int | None = None, lo: datetime = START, hi: datetime = END) -> None:
        """Own device and home IP, plus logins (some through extra shared IPs/devices)."""
        did = self.device()
        self.cust_device[cid] = did
        self.use_device(did, cid, lo, hi - timedelta(days=int(self.r.integers(0, 40))))
        home = self.ip(self.r.choice(["RESIDENTIAL", "MOBILE"], p=[0.8, 0.2]), NATION[self.cust_cur[cid]])
        self.cust_ip[cid] = home
        for _ in range(n_logins if n_logins is not None else int(self.r.integers(6, 16))):
            ip_ = self.r.choice(list(extra_ips)) if extra_ips and self.r.random() < 0.6 else home
            dev = self.r.choice(list(extra_devices)) if extra_devices and self.r.random() < 0.5 else did
            self.login(cid, dev, ip_, self.rand_ts(lo, hi))

    # ------------------------------------------------------------------ background population
    def background(self, n_personal: int = 380, n_business: int = 45) -> None:
        for _ in range(n_personal):
            cid = self.customer(self.r.choice(list(CURRENCIES), p=HOME_P))
            self.account(cid, "CURRENT")
            if self.r.random() < 0.35:
                self.account(cid, self.r.choice(["SAVINGS", "WALLET"], p=[0.7, 0.3]),
                             "DORMANT" if self.r.random() < 0.05 else "ACTIVE")
            self.online_identity(cid)
        for _ in range(n_business):
            cid = self.customer(self.r.choice(list(CURRENCIES), p=HOME_P), business=True)
            self.account(cid, "BUSINESS")
            if self.r.random() < 0.3:
                self.account(cid, "BUSINESS")
            self.online_identity(cid)
        self.base_customers = list(self.cust_accounts)
        self.base_accounts = [a for c in self.base_customers for a in self.cust_accounts[c]]

        # carrier-grade NAT mobile IPs: a few customers each, a normal source of shared IPs
        for _ in range(12):
            nat = self.ip("MOBILE", self.r.choice(["GB", "IN", "SG", "AE"]))
            for cid in self.r.choice(self.base_customers, size=int(self.r.integers(2, 5)), replace=False):
                for _ in range(int(self.r.integers(1, 4))):
                    self.login(cid, self.cust_device[cid], nat, self.rand_ts())

        # Account-to-account transfers only: card/merchant spending would live in merchant_transactions,
        # which TRACE does not map. Salaries come from employers, rent goes to landlords, savings sweeps go
        # to the holder's own savings account, a little P2P between friends, and businesses pay suppliers
        # along a supply chain (so trade does not loop back on itself).
        personal = self.base_customers[:n_personal]
        biz = self.base_customers[n_personal:]
        main = {c: self.cust_accounts[c][0] for c in self.base_customers}
        by_cur = lambda cs, cur: [c for c in cs if self.cust_cur[c] == cur]  # noqa: E731
        months = [(START + timedelta(days=31 * m)).replace(day=1) for m in range(12)]

        def on(month: datetime, day: int, hour: int | None = None) -> datetime:
            h = hour if hour is not None else int(self.r.choice(24, p=HOURS_P))
            return month.replace(day=min(day, 28), hour=h, minute=int(self.r.integers(0, 60)))

        def pay(src: str, dst: str, amt: float, ts: datetime, ttype: str = "TRANSFER", channel: str | None = None):
            self.txn(src, dst, amt, ts, ttype, channel,
                     status=self.r.choice(["COMPLETED", "PENDING", "REVERSED"], p=[0.96, 0.025, 0.015]))

        payday = {b: int(self.r.integers(24, 29)) for b in biz}
        salary: dict[str, tuple[str, float]] = {}
        for c in personal:
            employers = by_cur(biz, self.cust_cur[c])
            if employers and self.r.random() < 0.8:
                b = self.r.choice(employers)
                salary[c] = (b, round(self.r.uniform(1800, 5200) * CURRENCIES[self.cust_cur[c]], 2))
                if self.r.random() < 0.5:
                    self.relate(c, b, "EMPLOYEE", "DECLARATION")
        landlords = list(self.r.choice(personal, size=len(personal) // 8, replace=False))

        for c in personal:
            cur, a = self.cust_cur[c], main[c]
            fx = CURRENCIES[cur]
            income = salary[c][1] if c in salary else self.r.uniform(900, 2500) * fx
            friends = [main[f] for f in self.r.choice([x for x in by_cur(personal, cur) if x != c],
                                                       size=int(self.r.integers(1, 4)), replace=False)]
            ll_pool = [x for x in by_cur(landlords, cur) if x != c]
            landlord = main[self.r.choice(ll_pool)] if ll_pool and self.r.random() < 0.6 else None
            rent, rent_day = income * self.r.uniform(0.25, 0.4), int(self.r.integers(1, 6))
            savings = self.cust_accounts[c][1] if len(self.cust_accounts[c]) > 1 else None
            for month in months:
                if c in salary:
                    b = salary[c][0]
                    pay(main[b], a, salary[c][1], on(month, payday[b], int(self.r.integers(9, 17))), "TRANSFER", "API")
                if landlord:
                    pay(a, landlord, rent, on(month, rent_day), "PAYMENT")
                if savings and self.r.random() < 0.6:
                    pay(a, savings, income * self.r.uniform(0.05, 0.2), on(month, int(self.r.integers(1, 29))),
                        "TRANSFER", "MOBILE")
                if savings and self.r.random() < 0.08:
                    pay(savings, a, income * self.r.uniform(0.1, 0.5), on(month, int(self.r.integers(1, 29))),
                        "TRANSFER", "MOBILE")
                for _ in range(int(self.r.poisson(1.4))):
                    pay(a, self.r.choice(friends), self.r.lognormal(np.log(60), 0.9) * fx,
                        on(month, int(self.r.integers(1, 29))), "TRANSFER", "MOBILE")
            for f in friends[:2] + ([landlord] if landlord else []):
                self.tables["beneficiaries"].append({
                    "beneficiary_id": self._id("beneficiaries", "BEN", 5), "customer_id": c, "account_id": f,
                    "registration_date": self.rand_ts(START - timedelta(days=200), START).date().isoformat(),
                    "beneficiary_type": "INDIVIDUAL"})

        for cur in CURRENCIES:
            chain = by_cur(biz, cur)
            for i, b in enumerate(chain):
                downstream = chain[i + 1:]
                if not downstream:
                    continue
                suppliers = list(self.r.choice(downstream, size=min(len(downstream), int(self.r.integers(1, 4))),
                                               replace=False))
                for s in suppliers:
                    base = self.r.lognormal(np.log(4000), 0.6) * CURRENCIES[cur]
                    for month in months:
                        for _ in range(int(self.r.integers(1, 3))):
                            pay(main[b], main[s], base * self.r.uniform(0.6, 1.5),
                                on(month, int(self.r.integers(1, 29)), int(self.r.integers(8, 18))), "WIRE", "API")
                    self.tables["beneficiaries"].append({
                        "beneficiary_id": self._id("beneficiaries", "BEN", 5), "customer_id": b,
                        "account_id": main[s], "registration_date": (START - timedelta(days=90)).date().isoformat(),
                        "beneficiary_type": "BUSINESS"})

        # side tables at their ordinary rates
        for _ in range(60):
            mid = self._id("merchants", "M", 4)
            self.tables["merchants"].append({
                "merchant_id": mid, "merchant_name": f"Demo Merchant {mid[1:]}",
                "merchant_category": self.r.choice(["GROCERY", "ECOMMERCE", "ELECTRONICS", "SERVICES", "TRAVEL"]),
                "owner_business_id": "", "registration_country": self.r.choice(["GB", "IN", "SG", "AE"])})
        for _ in range(120):
            cid = self.r.choice(self.base_customers)
            self.complaint(cid, self.r.choice(["PAYMENT_DISPUTE", "ACCOUNT_ACCESS", "UNAUTHORIZED_TRANSFER",
                                               "IDENTITY_MISUSE"], p=[0.55, 0.25, 0.12, 0.08]), self.rand_ts())
        for _ in range(60):
            a, b = self.r.choice(self.base_customers, size=2, replace=False)
            self.relate(a, b, self.r.choice(["KNOWN_CONTACT", "BUSINESS_ASSOCIATE", "FAMILY"], p=[0.6, 0.2, 0.2]),
                        self.r.choice(["DECLARATION", "PUBLIC_RECORD"]))
        for _ in range(35):
            cid = self.r.choice(self.base_customers)
            self.tables["watchlist_matches"].append({
                "watchlist_match_id": self._id("watchlist_matches", "WL", 5), "entity_id": cid,
                "list_type": self.r.choice(["PEP", "ADVERSE_MEDIA", "INTERNAL_WATCH", "SANCTIONS"], p=[0.4, 0.35, 0.2, 0.05]),
                "match_type": self.r.choice(["POSSIBLE", "FUZZY", "EXACT"], p=[0.6, 0.35, 0.05]),
                "match_confidence": round(float(self.r.uniform(0.35, 0.8)), 2),
                "source": self.r.choice(["SYNTHETIC_EXTERNAL_LIST", "SYNTHETIC_INTERNAL_LIST"])})

    def background_alerts(self) -> None:
        """Ordinary alert volume over the generated transactions; a small share of cases escalate."""
        idx = self.r.choice(self.n_background_txns, size=260, replace=False)
        for i in idx:
            self.alert(i, self.r.choice(["RAPID_MOVEMENT", "UNUSUAL_LOCATION", "STRUCTURING", "SHARED_DEVICE",
                                         "CIRCULAR_FLOW"], p=[0.3, 0.35, 0.15, 0.1, 0.1]),
                       self.r.choice(["LOW", "MEDIUM", "HIGH"], p=[0.6, 0.3, 0.1]),
                       case_status=self.r.choice([None, "CLOSED", "OPEN", "IN_REVIEW", "ESCALATED"],
                                                 p=[0.6, 0.3, 0.05, 0.03, 0.02]))

    def alert(self, i: int, rule: str, severity: str, case_status: str | None = None, case_type: str = "AML") -> None:
        t = self.txns[i]
        aid = self._id("alerts", "AL", 5)
        created = t["timestamp"] + timedelta(minutes=int(self.r.integers(5, 600)))
        self.tables["alerts"].append({"alert_id": aid, "account_id": t["sender_account_id"],
                                      "transaction_id": i, "rule": rule, "severity": severity, "created_at": created})
        if case_status:
            self.tables["investigation_cases"].append({
                "case_id": self._id("investigation_cases", "CASE", 5), "alert_id": aid,
                "investigator_id": f"INV{int(self.r.integers(1, 15)):04d}", "status": case_status,
                "case_type": case_type, "opened_at": created + timedelta(hours=int(self.r.integers(2, 72)))})

    def pick(self, cur: str, n: int, exclude: set[str] = frozenset()) -> list[str]:
        pool = [a for a in self.base_accounts if self.acct_cur[a] == cur and a not in exclude]
        return list(self.r.choice(pool, size=n, replace=False))

    def new_holders(self, n: int, cur: str, atype: str = "CURRENT", **kw) -> tuple[list[str], list[str]]:
        cids = [self.customer(cur, **kw) for _ in range(n)]
        return cids, [self.account(c, atype) for c in cids]

    # ------------------------------------------------------------------ planted scenarios
    def mule_network(self) -> None:
        """S1 (GBP): many payers -> collector, forwarded within minutes through intermediaries to cash-out
        accounts. Ring holders share one device and a VPN exit; complaints and an escalated prior case."""
        cur, typ = "GBP", "MULE_NETWORK"
        lo = datetime(2026, 2, 16)
        cids, accts = self.new_holders(6, cur, kyc="PENDING", risk="MEDIUM")
        collector, inter, cash = accts[0], accts[1:4], accts[4:6]
        ring_dev, vpn = self.device("MOBILE"), self.ip("VPN", "GB")
        for c in cids:
            self.online_identity(c, extra_ips=[vpn], extra_devices=[ring_dev], lo=lo - timedelta(days=30))
            self.use_device(ring_dev, c, lo - timedelta(days=20), lo + timedelta(days=110))
        for a in inter + cash:
            self.tables["beneficiaries"].append({
                "beneficiary_id": self._id("beneficiaries", "BEN", 5), "customer_id": self.acct_cust[collector if a in inter else inter[0]],
                "account_id": a, "registration_date": (lo - timedelta(days=2)).date().isoformat(),
                "beneficiary_type": "INDIVIDUAL"})
        payers_all: set[str] = set()
        first_forward = None
        for wave in range(4):
            start = lo + timedelta(days=21 * wave)
            payers = self.pick(cur, int(self.r.integers(11, 16)), payers_all)
            payers_all |= set(payers)
            for p in payers:
                ts = self.rand_ts(start, start + timedelta(days=5))
                amt = self.r.uniform(450, 2400)
                self.txn(p, collector, amt, ts, "TRANSFER", "MOBILE")
                t1 = ts + timedelta(minutes=int(self.r.integers(6, 35)))
                mid = self.r.choice(inter)
                fwd = amt * self.r.uniform(0.86, 0.95)
                self.txn(collector, mid, fwd, t1, "TRANSFER", "MOBILE")
                first_forward = first_forward or len(self.txns) - 1
                t2 = t1 + timedelta(minutes=int(self.r.integers(8, 40)))
                self.txn(mid, self.r.choice(cash), fwd * self.r.uniform(0.9, 0.97), t2, "TRANSFER", "WEB")
            # cash-out accounts withdraw what arrived
            for c in cash:
                self.txn(c, self.r.choice(self.pick(cur, 3)), self.r.uniform(2500, 6000),
                         start + timedelta(days=6, hours=int(self.r.integers(9, 17))), "CASH_OUT", "ATM")
        hub = self.acct_cust[collector]
        for k, ctype in enumerate(["ACCOUNT_ACCESS", "IDENTITY_MISUSE", "UNAUTHORIZED_TRANSFER", "ACCOUNT_ACCESS"]):
            self.complaint(hub, ctype, lo + timedelta(days=24 + 3 * k, hours=11), "OPEN")
        self.alert(first_forward, "RAPID_MOVEMENT", "HIGH", case_status="ESCALATED", case_type="AML")
        for a, role in zip(accts, ["COLLECTOR", "INTERMEDIARY", "INTERMEDIARY", "INTERMEDIARY", "BENEFICIARY", "BENEFICIARY"]):
            self.label(a, role, typ)
        self.scenarios["S1_mule_network"] = {
            "typology": typ, "currency": cur, "collector": collector, "intermediaries": inter, "cash_out": cash,
            "payer_accounts": sorted(payers_all), "shared_device": ring_dev, "shared_ip": vpn,
            "expected": "fan-in at the collector, rapid pass-through on collector and intermediaries, shared "
                        "device and IP across unrelated holders, complaint cluster, prior escalated case"}

    def circular_flow(self) -> None:
        """S2 (USD): four unrelated companies pass ~the same amount round a loop within hours, repeatedly."""
        cur, typ = "USD", "CIRCULAR_FLOW"
        cids, accts = self.new_holders(4, cur, atype="BUSINESS", business=True, risk="MEDIUM")
        office = self.ip("CORPORATE", "AE")
        for c in cids:
            self.online_identity(c, extra_ips=[office])
        for k, start in enumerate([datetime(2026, 4, 7, 9), datetime(2026, 5, 12, 10), datetime(2026, 6, 16, 9),
                                   datetime(2026, 7, 21, 11), datetime(2026, 8, 25, 10)]):
            amt, ts = self.r.uniform(38000, 62000), start
            for h in range(4):
                self.txn(accts[h], accts[(h + 1) % 4], amt, ts, "WIRE", "API")
                amt *= self.r.uniform(0.97, 0.99)
                ts += timedelta(minutes=int(self.r.integers(70, 300)))
        self.tables["watchlist_matches"].append({
            "watchlist_match_id": self._id("watchlist_matches", "WL", 5), "entity_id": cids[2],
            "list_type": "SANCTIONS", "match_type": "FUZZY", "match_confidence": 0.88,
            "source": "SYNTHETIC_EXTERNAL_LIST"})
        for a, role in zip(accts, ["FUNDER", "INTERMEDIARY", "INTERMEDIARY", "INTERMEDIARY"]):
            self.label(a, role, typ)
        self.scenarios["S2_circular_flow"] = {
            "typology": typ, "currency": cur, "loop": accts, "shared_ip": office, "watchlist_customer": cids[2],
            "expected": "4-hop cycles with near-equal amounts, rapid pass-through, shared corporate IP across "
                        "unrelated companies, fuzzy sanctions potential match"}

    def structuring(self) -> None:
        """S3 (USD): three holders send many payments just under 10,000 to one account in a week; that account
        forwards them on within the hour. The three holders use one device."""
        cur, typ = "USD", "FAN_IN_FAN_OUT"
        cids, smurfs = self.new_holders(3, cur, kyc="VERIFIED", risk="LOW")
        _, (recv,) = self.new_holders(1, cur, risk="MEDIUM")
        _, (out,) = self.new_holders(1, cur, atype="BUSINESS", business=True)
        dev = self.device("MOBILE")
        for c in cids:
            self.online_identity(c, extra_devices=[dev])
            self.use_device(dev, c, datetime(2026, 5, 1), datetime(2026, 7, 31))
        for c in (self.acct_cust[recv], self.acct_cust[out]):
            self.online_identity(c)
        for week in (datetime(2026, 5, 18), datetime(2026, 6, 22), datetime(2026, 7, 20)):
            for s in smurfs:
                for _ in range(int(self.r.integers(4, 7))):
                    ts = self.rand_ts(week, week + timedelta(days=6))
                    amt = self.r.uniform(9050, 9950)
                    self.txn(s, recv, amt, ts, "TRANSFER", self.r.choice(["BRANCH", "MOBILE"]))
                    self.txn(recv, out, amt * self.r.uniform(0.92, 0.98),
                             ts + timedelta(minutes=int(self.r.integers(10, 50))), "WIRE", "WEB")
        for a, role in zip(smurfs + [recv, out], ["FUNDER", "FUNDER", "FUNDER", "COLLECTOR", "BENEFICIARY"]):
            self.label(a, role, typ)
        self.scenarios["S3_structuring"] = {
            "typology": typ, "currency": cur, "senders": smurfs, "receiver": recv, "onward": out,
            "shared_device": dev,
            "expected": "structuring just under a 10,000 USD mark (detected from the amount distribution), "
                        "fan-in and rapid pass-through at the receiver, shared device across the senders"}

    def layering_burst(self) -> None:
        """S4 (SGD): one large inbound wire is split into many transfers within an hour, which are passed on
        within minutes to two consolidation accounts. Happens twice."""
        cur, typ = "SGD", "LAYERING"
        _, (hub,) = self.new_holders(1, cur, atype="BUSINESS", business=True, risk="HIGH")
        _, (origin,) = self.new_holders(1, cur, atype="BUSINESS", business=True)
        lcids, layer = self.new_holders(14, cur, kyc="PENDING")
        _, sinks = self.new_holders(2, cur)
        for a in [hub, origin] + layer + sinks:
            self.online_identity(self.acct_cust[a], n_logins=int(self.r.integers(3, 8)), lo=datetime(2026, 1, 1))
        for start in (datetime(2026, 3, 10, 14, 5), datetime(2026, 8, 4, 15, 20)):
            total = self.r.uniform(170000, 210000)
            self.txn(origin, hub, total, start, "WIRE", "API")
            parts = self.r.dirichlet(np.ones(len(layer)) * 8) * total * 0.97
            ts = start + timedelta(minutes=12)
            for a, part in zip(layer, parts):
                ts += timedelta(minutes=int(self.r.integers(1, 4)))
                self.txn(hub, a, part, ts, "TRANSFER", "API")
                self.txn(a, sinks[int(self.r.integers(0, 2))], part * self.r.uniform(0.93, 0.98),
                         ts + timedelta(minutes=int(self.r.integers(9, 45))), "TRANSFER", "MOBILE")
        for a, role in [(origin, "FUNDER"), (hub, "INTERMEDIARY")] + [(a, "INTERMEDIARY") for a in layer] + \
                [(a, "BENEFICIARY") for a in sinks]:
            self.label(a, role, typ)
        self.scenarios["S4_layering_burst"] = {
            "typology": typ, "currency": cur, "origin": origin, "hub": hub, "layer": layer, "sinks": sinks,
            "expected": "burst velocity and fan-out at the hub, rapid pass-through on the layer accounts, "
                        "fan-in at the two sinks"}

    def payroll_lookalike(self) -> None:
        """L1 (INR) LEGITIMATE: a company pays 20 staff the same salary on the same day every month and all
        log in from the office network. Looks like fan-out + shared IP; should be explained by PAYROLL and
        OFFICE_NETWORK."""
        cur = "INR"
        (emp_c,), (emp,) = self.new_holders(1, cur, atype="BUSINESS", business=True, risk="LOW", kyc="VERIFIED")
        staff_c, staff = self.new_holders(20, cur, risk="LOW", kyc="VERIFIED")
        office = self.ip("CORPORATE", "IN")
        for c in [emp_c] + staff_c:
            self.online_identity(c, extra_ips=[office])
        salary = {s: round(self.r.uniform(45000, 160000), -2) for s in staff}
        for m in range(12):
            when = (START.replace(day=1) + timedelta(days=32 * m)).replace(day=28, hour=9, minute=0)
            for k, s in enumerate(staff):
                self.txn(emp, s, salary[s], when + timedelta(minutes=k), "TRANSFER", "API")
        for c in staff_c:
            self.relate(c, emp_c, "EMPLOYEE", "PUBLIC_RECORD")
        self.scenarios["L1_payroll_lookalike"] = {
            "legitimate": True, "currency": cur, "employer": emp, "staff": staff, "office_ip": office,
            "expected": "fan-out and shared IP, explained by PAYROLL (regular cadence) and OFFICE_NETWORK"}

    def family_lookalike(self) -> None:
        """L2 (USD) LEGITIMATE: a household shares a tablet and moves money between its own members."""
        cur = "USD"
        cids, accts = self.new_holders(4, cur, kyc="VERIFIED", risk="LOW")
        tablet = self.device("TABLET")
        for c in cids:
            self.online_identity(c, extra_devices=[tablet])
            self.use_device(tablet, c, START, END)
        for i, a in enumerate(cids):
            for b in cids[i + 1:]:
                self.relate(a, b, "FAMILY", "PUBLIC_RECORD")
        for _ in range(80):
            s, d = self.r.choice(accts, size=2, replace=False)
            self.txn(s, d, self.r.lognormal(np.log(120), 0.8), self.rand_ts(), "TRANSFER", "MOBILE")
        self.scenarios["L2_family_lookalike"] = {
            "legitimate": True, "currency": cur, "accounts": accts, "shared_device": tablet,
            "expected": "shared device only; FAMILY relationships explain it; should not become a case alone"}

    # ------------------------------------------------------------------ output
    def finish(self) -> None:
        order = sorted(range(len(self.txns)), key=lambda i: self.txns[i]["timestamp"])
        new_id = {old: f"T{k + 1:08d}" for k, old in enumerate(order)}
        self.txns = [dict(self.txns[i], transaction_id=new_id[i]) for i in order]
        for al in self.tables["alerts"]:
            al["transaction_id"] = new_id[al["transaction_id"]]

    def write(self, out: Path, seed: int) -> None:
        out.mkdir(parents=True, exist_ok=True)
        cols = {"transactions": ["transaction_id", "sender_account_id", "receiver_account_id", "amount", "currency",
                                 "timestamp", "transaction_type", "channel", "status"]}
        rows = {"transactions": self.txns, **self.tables}
        for name, data in rows.items():
            header = cols.get(name) or list(data[0])
            with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=header)
                w.writeheader()
                for r in data:
                    w.writerow({k: (v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v)
                                for k, v in r.items() if k in header})
        manifest = {"name": "TRACE-DEMO", "synthetic": True, "seed": seed, "period": [str(START), str(END)],
                    "rows": {k: len(v) for k, v in rows.items()}, "planted_scenarios": self.scenarios}
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (out / "README.txt").write_text(README, encoding="utf-8")


README = """TRACE-DEMO synthetic dataset
============================

FICTIONAL DATA generated by scripts/generate_demo_dataset.py (seeded, reproducible). No real people,
accounts or institutions. Same table/column layout as SIFTLINE v1.0, so config/mapping.yaml reads it
unchanged (point the source paths here, or upload the CSVs on the Datasets screen).

What is in it
- Background: ~425 customers with habitual counterparties, one home currency each, heavy-tailed amounts,
  ordinary small-business payroll, mobile NAT IPs shared by a few customers, ordinary complaints, alerts,
  prior cases, watchlist hits and relationships.
- Planted scenarios (see manifest.json for the exact account ids):
  S1 mule network (GBP), S2 circular flow (USD), S3 structuring under 10,000 (USD),
  S4 layering burst (SGD).
- Legitimate look-alikes: L1 payroll with an office network (INR), L2 a family sharing a tablet (USD).
- suspicious_ring_members.csv lists the planted S1-S4 accounts. TRACE uses it for reporting only.

What it does and does not prove
- The scenarios were written to exercise TRACE's detectors. If TRACE surfaces them, that shows the
  pipeline works end to end. It is NOT evidence of real-world detection performance.
- Thresholds are still derived by the pipeline from this data's own distributions; nothing is preset.
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data/raw/TRACE_DEMO")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    b = Builder(a.seed)
    b.background()
    b.n_background_txns = len(b.txns)
    b.mule_network()
    b.circular_flow()
    b.structuring()
    b.layering_burst()
    b.payroll_lookalike()
    b.family_lookalike()
    b.background_alerts()
    b.finish()
    b.write(a.out, a.seed)
    print(f"wrote {a.out}: " + ", ".join(f"{k}={len(v)}" for k, v in {"transactions": b.txns, **b.tables}.items()))


if __name__ == "__main__":
    main()
