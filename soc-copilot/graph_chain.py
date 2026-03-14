import os
import logging
import importlib
from langchain_community.graphs import Neo4jGraph
from langchain.chains import GraphCypherQAChain

logger = logging.getLogger(__name__)


def get_neo4j_graph() -> Neo4jGraph | None:
    """Create Neo4jGraph once at startup; return None if unavailable."""
    try:
        url = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        username = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "mayasec_neo4j")
        return Neo4jGraph(url=url, username=username, password=password)
    except Exception as e:
        logger.error(f"Neo4j connection failed: {e}")
        return None


def get_llm():
    """Prefer ChatOpenAI when OPENAI_API_KEY exists; fall back to ChatOllama."""
    if os.getenv("OPENAI_API_KEY"):
        try:
            openai_mod = importlib.import_module("langchain_openai")
            ChatOpenAI = getattr(openai_mod, "ChatOpenAI")
            return ChatOpenAI(model="gpt-4o", temperature=0)
        except Exception as e:
            logger.warning(f"ChatOpenAI initialization failed: {e}")
    else:
        logger.info("OPENAI_API_KEY not found; falling back to ChatOllama.")

    ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")

    try:
        ollama_mod = importlib.import_module("langchain_community.chat_models")
        ChatOllama = getattr(ollama_mod, "ChatOllama")
        return ChatOllama(model="llama3.2:3b", temperature=0, base_url=ollama_url)
    except Exception:
        try:
            ollama_mod = importlib.import_module("langchain_ollama")
            ChatOllama = getattr(ollama_mod, "ChatOllama")
            return ChatOllama(model="llama3.2:3b", temperature=0, base_url=ollama_url)
        except Exception as e:
            logger.critical(f"No LLM backend available (ChatOllama failed): {e}")
            return None


def get_cypher_chain(graph: Neo4jGraph, llm) -> GraphCypherQAChain | None:
    """Create GraphCypherQAChain with safe fallback to None."""
    if graph is None or llm is None:
        return None

    try:
        return GraphCypherQAChain.from_llm(
            llm=llm,
            graph=graph,
            verbose=True,
            return_intermediate_steps=True,
            allow_dangerous_requests=True,
        )
    except Exception as e:
        logger.error(f"Failed to create GraphCypherQAChain: {e}")
        return None


def run_cypher_query(chain: GraphCypherQAChain, question: str) -> dict:
    """Execute a graph QA query and normalize response for API callers."""
    if chain is None:
        return {
            "answer": "Graph database not available. Try asking about statistics instead.",
            "cypher_used": None,
            "raw_results": [],
        }

    try:
        result = chain.invoke({"query": question})

        answer = result.get("result", "No answer generated")
        intermediate = result.get("intermediate_steps", [])
        cypher_used = None
        raw_results = []

        for step in intermediate:
            if isinstance(step, dict):
                if "query" in step:
                    cypher_used = step["query"]
                if "context" in step:
                    raw_results = step["context"]

        return {
            "answer": answer,
            "cypher_used": cypher_used,
            "raw_results": raw_results,
        }
    except Exception as e:
        logger.error(f"Cypher chain query failed: {e}")
        return {
            "answer": f"Query failed: {str(e)}",
            "cypher_used": None,
            "raw_results": [],
        }
