"""
Enhanced FastMCP server with improved functionality and error handling.

Usage:
    uv run server enhanced_fastmcp stdio
    # or for HTTP transport:
    uv run server enhanced_fastmcp http
"""

import logging
from typing import List, Dict, Any
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, ImageContent, EmbeddedResource

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create an MCP server with better description
mcp = FastMCP(
    "bill-enhanced-demo",
    version="1.0.0",
    description="Enhanced MCP server with mathematical tools, greetings, and utilities"
)


# =============================================================================
# TOOLS - Functions that can be called by the AI
# =============================================================================

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    logger.info(f"Adding {a} + {b}")
    return a + b


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers together."""
    logger.info(f"Multiplying {a} * {b}")
    return a * b


@mcp.tool()
def calculate_stats(numbers: List[float]) -> Dict[str, float]:
    """Calculate basic statistics for a list of numbers."""
    if not numbers:
        raise ValueError("Numbers list cannot be empty")

    sorted_numbers = sorted(numbers)
    n = len(numbers)

    # Calculate statistics
    total = sum(numbers)
    mean = total / n

    # Median calculation
    if n % 2 == 0:
        median = (sorted_numbers[n//2 - 1] + sorted_numbers[n//2]) / 2
    else:
        median = sorted_numbers[n//2]

    # Variance and standard deviation
    variance = sum((x - mean) ** 2 for x in numbers) / n
    std_dev = variance ** 0.5

    logger.info(f"Calculated stats for {n} numbers")

    return {
        "count": n,
        "sum": total,
        "mean": mean,
        "median": median,
        "min": min(numbers),
        "max": max(numbers),
        "variance": variance,
        "standard_deviation": std_dev
    }


@mcp.tool()
def format_text(text: str, style: str = "title") -> str:
    """Format text in different styles."""
    styles = {
        "title": lambda t: t.title(),
        "upper": lambda t: t.upper(),
        "lower": lambda t: t.lower(),
        "reverse": lambda t: t[::-1],
        "capitalize": lambda t: t.capitalize(),
        "snake_case": lambda t: t.lower().replace(" ", "_"),
        "kebab_case": lambda t: t.lower().replace(" ", "-")
    }

    if style not in styles:
        available_styles = ", ".join(styles.keys())
        raise ValueError(f"Invalid style '{style}'. Available styles: {available_styles}")

    result = styles[style](text)
    logger.info(f"Formatted text with style '{style}'")
    return result


# =============================================================================
# RESOURCES - Data that can be read by the AI
# =============================================================================

@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting for someone."""
    if not name.strip():
        raise ValueError("Name cannot be empty")

    greeting = f"Hello, {name.strip()}! Welcome to the Enhanced MCP Server. 🎉"
    logger.info(f"Generated greeting for {name}")
    return greeting


@mcp.resource("math://formulas/{category}")
def get_math_formulas(category: str) -> str:
    """Get mathematical formulas by category."""
    formulas = {
        "geometry": """
# Geometry Formulas

## Area Formulas:
- Circle: A = πr²
- Rectangle: A = l × w
- Triangle: A = ½ × b × h
- Square: A = s²

## Volume Formulas:
- Sphere: V = (4/3)πr³
- Cylinder: V = πr²h
- Cube: V = s³
- Rectangular prism: V = l × w × h
        """,
        "algebra": """
# Algebra Formulas

## Quadratic Formula:
x = (-b ± √(b² - 4ac)) / 2a

## Distance Formula:
d = √((x₂-x₁)² + (y₂-y₁)²)

## Slope Formula:
m = (y₂-y₁) / (x₂-x₁)

## Point-Slope Form:
y - y₁ = m(x - x₁)
        """,
        "statistics": """
# Statistics Formulas

## Mean:
μ = (Σx) / n

## Variance:
σ² = Σ(x - μ)² / n

## Standard Deviation:
σ = √(σ²)

## Z-Score:
z = (x - μ) / σ
        """
    }

    if category not in formulas:
        available_categories = ", ".join(formulas.keys())
        raise ValueError(f"Unknown category '{category}'. Available: {available_categories}")

    logger.info(f"Retrieved {category} formulas")
    return formulas[category]


@mcp.resource("server://info")
def get_server_info() -> str:
    """Get information about this MCP server."""
    info = f"""
# Enhanced MCP Server Information

**Server Name:** {mcp.name}
**Version:** 1.0.0
**Description:** Enhanced MCP server with mathematical tools, greetings, and utilities

## Available Tools:
- add(a, b) - Add two numbers
- multiply(a, b) - Multiply two numbers  
- calculate_stats(numbers) - Calculate statistics for a list of numbers
- format_text(text, style) - Format text in different styles

## Available Resources:
- greeting://{{name}} - Get personalized greetings
- math://formulas/{{category}} - Get mathematical formulas (geometry, algebra, statistics)
- server://info - This information page

## Available Prompts:
- greet_user - Generate greeting prompts
- analyze_data - Generate data analysis prompts
    """

    logger.info("Retrieved server information")
    return info.strip()


# =============================================================================
# PROMPTS - Templates for AI interactions
# =============================================================================

@mcp.prompt()
def greet_user(name: str, style: str = "friendly") -> str:
    """Generate a greeting prompt for a user."""
    styles = {
        "friendly": "Please write a warm, friendly greeting",
        "formal": "Please write a formal, professional greeting",
        "casual": "Please write a casual, relaxed greeting",
        "enthusiastic": "Please write an enthusiastic, energetic greeting",
        "professional": "Please write a courteous, business-appropriate greeting"
    }

    if style not in styles:
        available_styles = ", ".join(styles.keys())
        raise ValueError(f"Unknown style '{style}'. Available styles: {available_styles}")

    prompt = f"{styles[style]} for someone named {name}. Make it personal and engaging."
    logger.info(f"Generated greeting prompt for {name} in {style} style")
    return prompt


@mcp.prompt()
def analyze_data(data_type: str = "numerical", focus: str = "trends") -> str:
    """Generate a data analysis prompt."""
    prompts = {
        ("numerical", "trends"): "Analyze the numerical data and identify key trends, patterns, and outliers. Provide insights about what the data reveals.",
        ("numerical", "statistics"): "Perform a comprehensive statistical analysis of the numerical data. Include measures of central tendency, variability, and distribution characteristics.",
        ("text", "sentiment"): "Analyze the text data for sentiment, tone, and emotional indicators. Identify positive, negative, and neutral elements.",
        ("text", "themes"): "Identify key themes, topics, and recurring patterns in the text data. Categorize and summarize the main concepts.",
        ("mixed", "overview"): "Provide a comprehensive analysis of the mixed data types. Identify relationships, patterns, and key insights across all data elements."
    }

    key = (data_type, focus)
    if key not in prompts:
        available_combinations = [f"{dt}/{f}" for dt, f in prompts.keys()]
        raise ValueError(f"Unknown combination '{data_type}/{focus}'. Available: {', '.join(available_combinations)}")

    prompt = prompts[key]
    logger.info(f"Generated analysis prompt for {data_type} data focusing on {focus}")
    return prompt


# =============================================================================
# SERVER CONFIGURATION AND STARTUP
# =============================================================================

def configure_server():
    """Configure server settings."""
    # Server settings
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8080

    # Add startup logging
    logger.info(f"Starting {mcp.name} server...")
    logger.info(f"Available tools: {len(mcp._tools)} tools")
    logger.info(f"Available resources: {len(mcp._resources)} resources")
    logger.info(f"Available prompts: {len(mcp._prompts)} prompts")


if __name__ == "__main__":
    configure_server()

    # Run with streamable HTTP transport (better for development)
    # You can also use 'stdio' for standard input/output transport
    try:
        mcp.run(transport='streamable-http')
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise