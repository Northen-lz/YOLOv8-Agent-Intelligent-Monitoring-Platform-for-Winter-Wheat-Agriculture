# -*- coding: utf-8 -*-
"""
Hello-Agents Neo4j 图存储
对齐文档第八章 8.2 存储后端层：Neo4jGraphStore（知识图谱管理）

职责：
- 连接 Neo4j（bolt 协议）
- 实体节点（Entity）+ 关系边（RELATES）管理，含 user_id 隔离
- 图谱检索：根据查询实体名找相关记忆
- 索引创建

语义记忆使用：
- upsert_entity(name, memory_id, user_id)  实体引用记忆
- create_relation(a, rel, b, memory_id)    关系引用记忆
- find_memories_for_entities(names)        图检索返回 {memory_id: score}

日志对齐文档（PDF 页 235）：
✅ 成功连接到Neo4j服务: {uri}
✅ Neo4j索引创建完成
"""

import logging
from typing import Dict, List, Optional

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


class Neo4jGraphStore:
    """Neo4j 图存储"""

    def __init__(
            self,
            uri: Optional[str] = None,
            username: Optional[str] = None,
            password: Optional[str] = None,
            database: Optional[str] = None,
            **kwargs,
    ):
        from ..base import MemoryConfig
        cfg = MemoryConfig()
        self.uri = uri or cfg.neo4j_uri
        self.username = username or cfg.neo4j_username
        self.password = password or cfg.neo4j_password
        self.database = database or "neo4j"

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.username, self.password),
        )
        self.connected = True
        self._connect()
        if self.connected:
            try:
                self.create_indexes()
            except Exception as e:
                print(f"⚠️ Neo4j索引创建失败（降级继续）: {e}")
                logger.warning("Neo4j索引创建失败", exc_info=True)

    # ---------------- 初始化 ----------------

    def _connect(self):
        try:
            self.driver.verify_connectivity()
            print(f"✅ 成功连接到Neo4j服务: {self.uri}")
            self.connected = True
        except Exception as e:
            # 容错：Neo4j 未启动时不 raise（否则整站起不来），
            # 标记为未连接，具体操作返回友好错误提示。
            self.connected = False
            print(f"⚠️ Neo4j连接失败({self.uri})，图存储将降级为不可用: {e}")
            logger.warning("Neo4j连接失败（容错处理，后续操作将返回错误提示）")

    def create_indexes(self):
        """创建实体名称与用户隔离索引"""
        self._require_connected()
        statements = [
            "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.user_id)",
            "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.name)",
        ]
        with self.driver.session(database=self.database) as session:
            for stmt in statements:
                session.run(stmt)
        print("✅ Neo4j索引创建完成")

    def _require_connected(self):
        """未连接时抛出明确错误（供调用方 catch 后给出友好提示）"""
        if not self.connected:
            raise RuntimeError(
                f"Neo4j 服务未连接({self.uri})，该操作不可用。"
                "请先启动 Neo4j。")

    # ---------------- 实体与关系 ----------------

    def upsert_entity(
            self,
            name: str,
            memory_id: Optional[str] = None,
            user_id: str = "default_user",
            properties: Optional[Dict] = None,
    ):
        """创建或更新实体节点（实体可被多条记忆引用）"""
        self._require_connected()
        props = dict(properties or {})
        create_props = dict(props)
        create_props["memory_ids"] = props.get("memory_ids", [])
        # 更新时排除 memory_ids，避免 ON MATCH 覆盖清空已有引用列表
        update_props = {k: v for k, v in props.items() if k != "memory_ids"}
        cypher = (
            "MERGE (n:Entity {name: $name, user_id: $user_id}) "
            "ON CREATE SET n += $create_props "
            "ON MATCH SET n += $update_props "
            "RETURN n.name"
        )
        with self.driver.session(database=self.database) as session:
            session.run(
                cypher,
                name=name,
                user_id=user_id,
                create_props=create_props,
                update_props=update_props,
            )
        if memory_id:
            self._link_entity_to_memory(name, memory_id, user_id)

    def _link_entity_to_memory(self, name: str, memory_id: str, user_id: str):
        """将记忆ID追加到实体节点的 memory_ids 列表"""
        self._require_connected()
        cypher = (
            "MATCH (n:Entity {name: $name, user_id: $user_id}) "
            "SET n.memory_ids = CASE "
            "  WHEN $memory_id IN n.memory_ids THEN n.memory_ids "
            "  ELSE n.memory_ids + [$memory_id] END "
            "RETURN n.memory_ids"
        )
        with self.driver.session(database=self.database) as session:
            session.run(cypher, name=name, memory_id=memory_id, user_id=user_id)

    def create_relation(
            self,
            source: str,
            relation: str,
            target: str,
            memory_id: Optional[str] = None,
            user_id: str = "default_user",
            properties: Optional[Dict] = None,
    ):
        """创建实体间关系（边）"""
        self._require_connected()
        props = dict(properties or {})
        cypher = (
            "MERGE (a:Entity {name: $source, user_id: $user_id}) "
            "MERGE (b:Entity {name: $target, user_id: $user_id}) "
            "MERGE (a)-[r:RELATES {type: $relation}]->(b) "
            "SET r += $props "
            "SET r.memory_ids = CASE "
            "  WHEN $memory_id IS NULL THEN r.memory_ids "
            "  WHEN $memory_id IN r.memory_ids THEN r.memory_ids "
            "  ELSE COALESCE(r.memory_ids, []) + [$memory_id] END "
            "RETURN r"
        )
        with self.driver.session(database=self.database) as session:
            session.run(
                cypher,
                source=source,
                target=target,
                relation=relation,
                user_id=user_id,
                props=props,
                memory_id=memory_id,
            )

    # ---------------- 图谱检索 ----------------

    def find_memories_for_entities(
            self,
            entity_names: List[str],
            user_id: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        根据查询中的实体名在图谱中匹配相关记忆（含 1-hop 关系邻居召回）。
        返回 {memory_id: 匹配分数}：
        - 直接命中实体：分数 = 命中实体数 / 查询实体数（保持原语义）
        - 关系邻居（经 RELATES 边相连的实体）：0.5 × 基础分，作为图结构补充
        （优化：原实现只按实体名取 memory_ids，RELATES 边对检索无贡献；
         加入邻居后「干旱 -影响-> 拔节期」这类关系能带出关联知识点）
        """
        if not entity_names:
            return {}
        self._require_connected()
        names = [n for n in entity_names if n]
        if not names:
            return {}

        cypher = (
            "MATCH (q:Entity) "
            "WHERE ($user_id IS NULL OR q.user_id = $user_id) "
            "  AND (q.name IN $names OR "
            "       any(x IN $names WHERE toLower(q.name) CONTAINS toLower(x))) "
            "OPTIONAL MATCH (q)-[r:RELATES]->(nb:Entity) "
            "RETURN q.memory_ids AS memory_ids, "
            "       collect(nb.memory_ids) AS neighbor_memory_ids"
        )
        with self.driver.session(database=self.database) as session:
            records = session.run(
                cypher,
                names=names,
                user_id=user_id,
            ).data()

        scores: Dict[str, float] = {}
        base = 1.0 / len(names)
        for rec in records:
            # 直接命中实体 → 基础分
            for mid in rec.get("memory_ids") or []:
                scores[mid] = scores.get(mid, 0.0) + base
            # 关系邻居实体 → 0.5 基础分（图结构补充，不喧宾夺主）
            for mids in rec.get("neighbor_memory_ids") or []:
                for mid in mids or []:
                    scores[mid] = scores.get(mid, 0.0) + 0.5 * base
        return scores

    def get_graph_stats(self, user_id: Optional[str] = None) -> Dict[str, int]:
        """图谱统计（实体数 / 关系数）"""
        self._require_connected()
        ent_cypher = "MATCH (n:Entity) RETURN count(n) AS c"
        rel_cypher = "MATCH ()-[r:RELATES]->() RETURN count(r) AS c"
        if user_id:
            ent_cypher = ("MATCH (n:Entity {user_id: $user_id}) "
                          "RETURN count(n) AS c")
            rel_cypher = ("MATCH (a:Entity {user_id: $user_id})-[r:RELATES]->() "
                          "RETURN count(r) AS c")
        with self.driver.session(database=self.database) as session:
            ents = session.run(ent_cypher, user_id=user_id).single()["c"]
            rels = session.run(rel_cypher, user_id=user_id).single()["c"]
        return {"entities": ents, "relations": rels}

    def clear(self, user_id: Optional[str] = None) -> int:
        """清空图谱（可指定用户），返回删除的实体数"""
        self._require_connected()
        if user_id:
            cypher = (
                "MATCH (n:Entity {user_id: $user_id}) "
                "DETACH DELETE n RETURN count(n) AS c"
            )
        else:
            cypher = "MATCH (n) DETACH DELETE n RETURN count(n) AS c"
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, user_id=user_id).single()
            return result["c"] if result else 0

    def close(self):
        try:
            self.driver.close()
        except Exception:
            pass
