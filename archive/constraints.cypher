// Constraints and indexes for Neo4j
// Ensure Neo4j version supports IF NOT EXISTS variants (Neo4j 4.3+)

CREATE CONSTRAINT IF NOT EXISTS legalact_id_unique FOR (n:LegalAct) REQUIRE n.id IS UNIQUE;

CREATE INDEX IF NOT EXISTS legalact_pub_year_pos_idx FOR (n:LegalAct) ON (n.publisher, n.year, n.position);

CREATE CONSTRAINT IF NOT EXISTS article_id_unique FOR (a:Article) REQUIRE a.id IS UNIQUE;

CREATE INDEX IF NOT EXISTS article_number_idx FOR (a:Article) ON (a.number);
