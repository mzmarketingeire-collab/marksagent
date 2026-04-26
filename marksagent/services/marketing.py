class MarketingService:
    """Marketing content generation"""
    
    def __init__(self, config):
        self.config = config
        
    async def generate_post(self, topic: str, platform: str = "linkedin") -> dict:
        """Generate marketing post"""
        
        # Templates for different platforms
        templates = {
            "linkedin": {
                "hook": f"🚀 {topic.title()}: Here's what you need to know",
                "body": "In today's fast-paced market, staying ahead means {topic}.\n\nHere's the truth:\n\n✅ Focus on what matters\n✅ Build genuine connections\n✅ Deliver real value\n\nThe rest is just noise.\n\nWhat's your experience? Drop a comment below 👇",
                "cta": "Follow for more insights"
            },
            "twitter": {
                "hook": f"🧵 {topic.title()}",
                "body": "1/ The biggest mistake people make with {topic}\n\n2/ It's not about the tactics, it's about the mindset\n\n3/ Here's what actually works:\n\n- Focus on value\n- Build relationships\n- Stay consistent\n\n4/ The rest is noise.\n\n5/ Save this for later 📌",
                "cta": "Follow for more"
            },
            "instagram": {
                "hook": f"💡 {topic.title()}",
                "body": "Here's the truth about {topic}:\n\n⬆️ Swipe for the full breakdown\n\nSave this post! 📌\n\n#business #growth #entrepreneur"
            }
        }
        
        template = templates.get(platform, templates["linkedin"])
        
        return {
            "platform": platform,
            "topic": topic,
            "hook": template["hook"],
            "body": template["body"],
            "cta": template["cta"]
        }
    
    async def generate_email(self, subject: str, content: str) -> dict:
        """Generate marketing email"""
        
        return {
            "subject": subject,
            "body": f"""Hi,

{content}

Best regards,
Your AI Assistant

---
Want to learn more? Book a call with us.
""",
            "cta": "Book a call"
        }