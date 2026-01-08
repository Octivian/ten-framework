import axios from "axios";
import { type NextRequest, NextResponse } from "next/server";

/**
 * Handles the POST request to start an agent.
 *
 * @param request - The NextRequest object representing the incoming request.
 * @returns A NextResponse object representing the response to be sent back to the client.
 */
export async function POST(request: NextRequest) {
  try {
    const { AGENT_SERVER_URL } = process.env;

    // Check if environment variables are available
    if (!AGENT_SERVER_URL) {
      throw "Environment variables are not available";
    }

    const body = await request.json();
    const {
      request_id,
      channel_name,
      user_uid,
      graph_name,
      language,
      voice_type,
      properties,
      prompt_params,  // 简化的顶级参数，用于模板渲染
    } = body;

    // Build properties object
    let finalProperties = properties || {};

    // If prompt_params is provided, inject into v2v.prompt_params for template rendering
    if (prompt_params && Object.keys(prompt_params).length > 0) {
      finalProperties = {
        ...finalProperties,
        v2v: {
          ...(finalProperties.v2v || {}),
          prompt_params: prompt_params,
        },
      };
    }

    console.log("[route.tsx] prompt_params:", JSON.stringify(prompt_params));
    console.log("[route.tsx] finalProperties:", JSON.stringify(finalProperties));

    // Send a POST request to start the agent
    const response = await axios.post(`${AGENT_SERVER_URL}/start`, {
      request_id,
      channel_name,
      user_uid,
      graph_name,
      // Get the graph properties based on the graph name, language, and voice type
      properties: Object.keys(finalProperties).length > 0 ? finalProperties : undefined,
    });

    const responseData = response.data;

    return NextResponse.json(responseData, { status: response.status });
  } catch (error) {
    if (error instanceof Response) {
      const errorData = await error.json();
      return NextResponse.json(errorData, { status: error.status });
    } else {
      return NextResponse.json(
        { code: "1", data: null, msg: "Internal Server Error" },
        { status: 500 }
      );
    }
  }
}
