/**
 * Groq Llama 3.3 one-sentence review summariser.
 *
 * Mirrors the OpenAI-compatible client pattern from task2/agent.py.
 * Brief asks for Claude; we deviated to Groq Llama because Claude
 * credits weren't available at build time (same deviation flagged in
 * Task 2's README).
 *
 * No tool use here — a single short non-streaming completion. Fast,
 * no need for the salvage-failed-tool-call path Task 2 has.
 */
import OpenAI from "openai";
import type { Review } from "./reviews.server";

declare global {
  // eslint-disable-next-line no-var
  var __groqClient: OpenAI | undefined;
}

function getClient(): OpenAI {
  if (!global.__groqClient) {
    if (!process.env.GROQ_API_KEY) {
      throw new Error(
        "GROQ_API_KEY not set in task4/teambeauty-reviews/.env",
      );
    }
    global.__groqClient = new OpenAI({
      apiKey: process.env.GROQ_API_KEY,
      baseURL: "https://api.groq.com/openai/v1",
    });
  }
  return global.__groqClient;
}

const MODEL = process.env.GROQ_MODEL || "llama-3.3-70b-versatile";

export async function summarizeReviews(reviews: Review[]): Promise<string> {
  if (reviews.length === 0) {
    return "No reviews yet.";
  }

  // Cap the input so a flood of reviews doesn't blow the context budget.
  const sample = reviews.slice(0, 50);
  const formatted = sample
    .map(
      (r, i) =>
        `${i + 1}. (${r.rating}/5) ${r.customer_name}: ${r.review_text}`,
    )
    .join("\n");

  const resp = await getClient().chat.completions.create({
    model: MODEL,
    max_tokens: 80,
    messages: [
      {
        role: "system",
        content:
          "You write one-sentence summaries of customer product reviews. Be specific about what customers like and any common complaint. No bullet lists. Output one sentence, under 25 words.",
      },
      {
        role: "user",
        content: `Summarise these ${sample.length} customer reviews in one sentence:\n\n${formatted}`,
      },
    ],
  });

  return (resp.choices[0]?.message?.content || "Summary unavailable.").trim();
}
