from neo4j import GraphDatabase

uri='bolt://localhost:7687'
user='neo4j'
password='neo4jpass'

driver = GraphDatabase.driver(uri, auth=(user, password))
with driver.session() as session:
    r = session.run('MATCH (n:LegalAct) RETURN count(n) AS cnt')
    cnt = r.single().get('cnt')
    print('LegalAct nodes:', cnt)
    r = session.run('MATCH ()-[r:AMENDS]->() RETURN count(r) AS cnt')
    print('AMENDS relationships:', r.single().get('cnt'))
    r = session.run('MATCH ()-[r:REPEALS]->() RETURN count(r) AS cnt')
    print('REPEALS relationships:', r.single().get('cnt'))

driver.close()
