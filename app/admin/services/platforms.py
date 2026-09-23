from ..schemas.catalog import DomainError, canonical, validate, RESOURCES
from ..schemas.contracts import EntityInput


class PlatformService:
    def __init__(self, review):
        self.review = review

    def _group(self, c, key):
        account = self.review.draft(c, key)
        if account["entity_type"] != "external_accounts":
            raise DomainError("외부 플랫폼 계정을 선택하세요.")
        targets = [{"$ref": account["client_ref"]}]
        if account["target_id"]:
            targets.append(account["target_id"])
        links = []
        for row in c.execute("SELECT id FROM draft_entities WHERE batch_id=? AND entity_type='artist_external_accounts' ORDER BY created_at,id", (account["batch_id"],)):
            draft = self.review.draft(c, row["id"])
            if draft["current_payload"].get("account_id") in targets:
                links.append(draft)
        return {"account": account, "artists": links}

    def detail(self, key):
        with self.review.local.connect() as c:
            return self._group(c, key)

    def save(self, body):
        batch_id = str(body.batch_id)
        r = self.review
        with r.local.connect(write=True) as c:
            r.ensure_editable(c, batch_id)
            previous = None
            if body.account.id:
                previous = self._group(c, str(body.account.id))
                if previous["account"]["batch_id"] != batch_id:
                    raise DomainError("다른 검수 묶음의 계정입니다.", 409)
                if {x["id"] for x in previous["artists"]} != {str(x.id) for x in body.artists if x.id}:
                    raise DomainError("연결 목록이 변경되었습니다. 다시 불러오세요.", 409)
            elif any(x.id for x in body.artists):
                raise DomainError("새 계정에는 기존 연결 초안을 지정할 수 없습니다.")
            account_ref = previous["account"]["client_ref"] if previous else body.account.client_ref
            seen = set()
            for link in body.artists:
                if previous:
                    old = next((x for x in previous["artists"] if x["id"] == str(link.id)), None)
                    if old and old["status"] == "excluded":
                        continue
                artist = canonical(link.data.get("artist_id"))
                if artist in seen:
                    raise DomainError("같은 아티스트를 중복 연결할 수 없습니다.")
                seen.add(artist)

            def persist(item, kind, data, old=None):
                if item.id:
                    current = r.draft(c, str(item.id))
                    if current["batch_id"] != batch_id or current["entity_type"] != kind or current["revision"] != item.revision:
                        raise DomainError("다른 창에서 수정되었습니다. 다시 불러오세요.", 409)
                    if current["status"] == "excluded":
                        if current["current_payload"] != data:
                            raise DomainError("제외한 연결을 수정하려면 먼저 다시 검수하세요.")
                        return current["id"]
                    if current["current_payload"] != data:
                        validate(kind, data, partial=current["operation"] == "update")
                        r._edit(c, current["id"], item.revision, data)
                    return current["id"]
                validate(kind, data)
                return r._create(c, batch_id, EntityInput(client_ref=item.client_ref, entity_type=kind, data=data))

            key = persist(body.account, "external_accounts", body.account.data)
            for link in body.artists:
                data = {**link.data, "account_id": {"$ref": account_ref}}
                if previous:
                    old = next((x for x in previous["artists"] if x["id"] == str(link.id)), None)
                    if old and old["status"] == "excluded":
                        data = link.data
                persist(link, "artist_external_accounts", data)
            result = self._group(c, key)
        return result

    def from_catalog(self, batch_id, account_id):
        r = self.review
        group = r.remote.platform_registration(account_id)
        with r.local.connect(write=True) as c:
            r.ensure_editable(c, batch_id)
            found = c.execute("SELECT id FROM draft_entities WHERE batch_id=? AND entity_type='external_accounts' AND target_id=?", (batch_id, account_id)).fetchone()
            if found:
                return self._group(c, found["id"])
            ref = "platform-account:" + str(account_id)
            def stage(kind, row, client_ref, data):
                return r._create(c, batch_id, EntityInput(
                    client_ref=client_ref, entity_type=kind, operation="update",
                    target_id=row["id"], expected_version=row["_version"], data=data))
            def payload(kind, row):
                return {f["name"]: row[f["name"]] for f in RESOURCES[kind]["fields"]}
            key = stage("external_accounts", group["account"], ref, payload("external_accounts", group["account"]))
            for link in group["artists"]:
                found_link = c.execute("SELECT id FROM draft_entities WHERE batch_id=? AND entity_type='artist_external_accounts' AND target_id=?", (batch_id, link["id"])).fetchone()
                if found_link:
                    continue
                data = payload("artist_external_accounts", link)
                data["account_id"] = {"$ref": ref}
                stage("artist_external_accounts", link, "platform-link:" + str(link["id"]), data)
            return self._group(c, key)

    @staticmethod
    def group_status(members):
        states = {m["status"] for m in members}
        if len(states) == 1:
            return next(iter(states))
        for state in ("blocked", "editing", "pending", "held"):
            if state in states:
                return state
        return "approved" if "approved" in states else "published" if "published" in states else "excluded"

    def _review_rows(self, c, batch_id):
        rows = [self.review.draft(c, row["id"]) for row in c.execute(
            "SELECT id FROM draft_entities WHERE batch_id=? ORDER BY created_at,id", (batch_id,))]
        accounts = [row for row in rows if row["entity_type"] == "external_accounts"]
        by_ref = {row["client_ref"]: row for row in accounts}
        by_id = {row["target_id"]: row for row in accounts if row["target_id"]}
        groups = {row["id"]: [row] for row in accounts}
        hidden = set()
        for row in rows:
            if row["entity_type"] != "artist_external_accounts":
                continue
            target = row["current_payload"].get("account_id")
            account = by_ref.get(target.get("$ref")) if isinstance(target, dict) else by_id.get(target) if isinstance(target, int) else None
            if account:
                groups[account["id"]].append(row)
                hidden.add(row["id"])
        result = []
        for row in rows:
            if row["id"] in hidden:
                continue
            members = groups.get(row["id"], [row])
            item = {**row, "_members": members}
            if row["id"] in groups:
                item["review_group"] = "platform"
                item["status"] = self.group_status(members)
                item["member_count"] = len(members)
            result.append(item)
        return result

    def review_counts(self, batch_id):
        with self.review.local.connect() as c:
            rows = self._review_rows(c, batch_id)
        counts = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return counts

    def review_page(self, batch_id, q="", status="", page=1, page_size=30):
        with self.review.local.connect() as c:
            items = self._review_rows(c, batch_id)
        # Group before filtering/pagination so linked drafts never split across pages.
        needle = q.casefold()
        items = [item for item in items if
                 (not status or item["status"] == status) and
                 (not needle or any(needle in (m["client_ref"] + canonical(m["current_payload"])).casefold()
                                    for m in item["_members"]))]
        total = len(items)
        return {"items": [{k:v for k,v in item.items() if k != "_members"}
                          for item in items[(page-1)*page_size:page*page_size]],
                "total":total, "page":page, "page_size":page_size}

    def next_review(self, key, q="", status="all", page_size=30):
        with self.review.local.connect() as c:
            current = self.review.draft(c, key)
            rows = self._review_rows(c, current["batch_id"])
        needle = q.casefold()
        rows = [row for row in rows if not needle or any(
            needle in (m["client_ref"] + canonical(m["current_payload"])).casefold() for m in row["_members"])]
        # A legacy individual link ID also resolves to its containing review item.
        parent = next((row for row in rows if any(m["id"] == key for m in row["_members"])), current)
        candidates = [row for row in rows if row["status"] == "pending" and
                      (row["created_at"], row["id"]) > (parent["created_at"], parent["id"])]
        if not candidates:
            return {"item":None}
        target = candidates[0]
        visible = [row for row in rows if status == "all" or row["status"] == "pending"]
        item = {k:v for k,v in target.items() if k != "_members"}
        if not item.get("review_group"):
            item = self.review.detail(item["id"])
        return {"item":item, "page": visible.index(target)//page_size+1}

    def review_group(self, key, body):
        with self.review.local.connect(write=True) as c:
            group = self._group(c, key)
            members = [group["account"], *group["artists"]]
            expected = {str(item.id): item.revision for item in body.items}
            if len(expected) != len(body.items) or expected != {m["id"]:m["revision"] for m in members}:
                raise DomainError("계정 또는 연결이 변경되었습니다. 다시 불러오세요.", 409)
            # Failures roll back approval of every member in this logical item.
            for member in members:
                if body.action == "approve" and member["status"] == "excluded" and member["id"] != key:
                    continue
                error = self.review._review(c, member["id"], member["revision"], body.action, body.note)
                if error:
                    raise error
            return self._group(c, key)
