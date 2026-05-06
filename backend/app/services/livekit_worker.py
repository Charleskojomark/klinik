import os
import logging
import asyncio
from dotenv import load_dotenv

# Load env variables so LiveKit CLI can find LIVEKIT_URL
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

from livekit import agents, rtc
from livekit.agents import AgentSession, JobContext
from livekit.plugins import openai

from app.config import get_settings
from app.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)


class KlinikVoiceWorker:
    """
    LiveKit agent that:
    1. Joins a LiveKit room
    2. Initializes Simli Avatar
    3. Listens to the Redis Event Bus for consultation completion
    4. Triggers the Avatar to speak the summary using TTS
    """

    def __init__(self, settings):
        self.settings = settings

    async def create_agent_session(self, ctx: JobContext):
        """
        Entry point called by LiveKit when a doctor joins a room.
        Sets up the Simli avatar and TTS pipeline.
        """
        logger.info(f"🎙️ Doctor joined room: {ctx.room.name}")

        # Setup TTS (We use OpenAI's TTS via LiveKit Cloud Inference or API Key)
        # We will use this to generate audio for Simli to lip-sync
        tts_plugin = openai.TTS()

        # Build the agent session
        session = AgentSession(
            tts=tts_plugin,
        )

        simli_avatar = None
        # Setup Simli Avatar (if configured)
        if self.settings.simli_api_key and self.settings.simli_face_id:
            try:
                from livekit.plugins import simli

                simli_avatar = simli.AvatarSession(
                    simli_config=simli.SimliConfig(
                        api_key=self.settings.simli_api_key,
                        face_id=self.settings.simli_face_id,
                    ),
                    avatar_participant_name="supervisor",
                )

                # Start avatar in the room
                await simli_avatar.start(session, room=ctx.room)
                logger.info("🤖 Simli avatar joined the room")
            except ImportError:
                logger.warning("Simli plugin not installed — avatar disabled")
            except Exception as e:
                logger.error(f"Simli avatar failed to start: {e}")

        # Start a background task to listen for the LangGraph completion event
        asyncio.create_task(self.listen_for_completion_and_speak(session, ctx.room.name))

        return session

    async def listen_for_completion_and_speak(self, session: AgentSession, room_name: str):
        """
        Listen to Redis for the 'workflow completed' event.
        When received, use the AgentSession TTS to speak the summary.
        Simli will automatically capture this audio and animate the avatar!
        """
        try:
            event_bus = await get_event_bus()
            logger.info("👂 LiveKit Worker listening for completion events...")
            
            # Since we don't have the exact session_id here, we listen to all events
            # In a real app, you would pass the session_id as room metadata
            pubsub = event_bus.redis.pubsub()
            await pubsub.subscribe("klinik-agent-events")

            async for message in pubsub.listen():
                if message["type"] == "message":
                    import json
                    try:
                        data = json.loads(message["data"])
                        # If the workflow is completed, grab the summary and speak it
                        if data.get("agent") == "workflow" and data.get("status") == "completed":
                            summary = data.get("output", "")
                            if summary:
                                logger.info(f"🗣️ Triggering Avatar Speech: {summary[:50]}...")
                                # Make the agent say the summary
                                # The session will route this text -> TTS -> Simli Avatar -> Room
                                await session.say(summary)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            logger.error(f"Error in Redis listener task: {e}")


# ──────────────────────────────────────────────
# Standalone LiveKit Agent Worker
# ──────────────────────────────────────────────

async def entrypoint(ctx: JobContext):
    """LiveKit agent entry point for doctor consultations."""
    settings = get_settings()
    worker = KlinikVoiceWorker(settings)

    await ctx.connect()
    logger.info(f"🏥 Klinik supervisor agent ready in room: {ctx.room.name}")
    session = await worker.create_agent_session(ctx)
    
    # Say a greeting when the room opens
    await session.say("Klinik system active. Waiting for consultation.")

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
