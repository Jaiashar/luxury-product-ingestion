# scraper/utils/session_manager.py - Fixed for concurrent access issues and special characters
"""Enhanced session management with better unique session naming."""

import time
import random
import string
import asyncio
import unicodedata
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

class SessionStatus(Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    EXPIRED = "expired"
    ROTATED = "rotated"

@dataclass
class SessionInfo:
    session_name: str
    site: str
    brand: str
    operation: str
    created_at: float
    last_used: float
    request_count: int
    error_count: int
    status: SessionStatus

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, SessionInfo] = {}
        self.blocked_sessions: set = set()
        self.last_request_time = 0
        self.min_request_gap = 1.0  # Minimum 1 second between requests
        
        # Session limits
        self.max_session_age = 3600  # 1 hour
        self.max_requests_per_session = 50
        self.max_errors_per_session = 5
        
        # User agents rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0'
        ]
    
    def _generate_unique_session_name(self, site: str, brand: str, operation: str) -> str:
        """Generate a more unique session name to avoid concurrent access - FIXED for special characters."""
        # Add milliseconds + random string for better uniqueness
        timestamp_ms = int(time.time() * 1000)
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        process_id = random.randint(10000, 99999)  # Simulate process ID
        
        # FIXED: Clean brand name for session - REMOVE ALL SPECIAL CHARACTERS
        clean_brand = brand.lower()
        # Remove accents and special characters using unicode normalization
        clean_brand = unicodedata.normalize('NFD', clean_brand)
        clean_brand = ''.join(c for c in clean_brand if unicodedata.category(c) != 'Mn')
        # Keep only alphanumeric characters
        clean_brand = ''.join(c for c in clean_brand if c.isalnum())[:10]
        
        # Clean operation name - only alphanumeric
        clean_operation = ''.join(c for c in operation if c.isalnum())[:15]
        
        session_name = f"{site}_{clean_brand}_{clean_operation}_{timestamp_ms}_{process_id}_{random_suffix}"
        
        # Debug: Print the cleaned session name
        print(f"🔧 Generated session: {session_name} (from brand: {brand})")
        
        # Ensure uniqueness by checking existing sessions
        base_name = session_name
        counter = 1
        while session_name in self.sessions:
            session_name = f"{base_name}_{counter}"
            counter += 1
            
        return session_name
    
    async def create_session(self, site: str, brand: str, operation: str) -> str:
        """Create a new session with enhanced uniqueness."""
        # Clean up old sessions first
        self._cleanup_old_sessions()
        
        # Generate unique session name
        session_name = self._generate_unique_session_name(site, brand, operation)
        
        # Create session info
        session_info = SessionInfo(
            session_name=session_name,
            site=site,
            brand=brand,
            operation=operation,
            created_at=time.time(),
            last_used=time.time(),
            request_count=0,
            error_count=0,
            status=SessionStatus.ACTIVE
        )
        
        self.sessions[session_name] = session_info
        
        print(f"🔄 Created session: {session_name}")
        return session_name
    
    def should_rotate_session(self, session_name: str) -> bool:
        """Check if session should be rotated."""
        if not session_name or session_name not in self.sessions:
            return True
        
        session = self.sessions[session_name]
        current_time = time.time()
        
        # Check various rotation conditions
        checks = [
            session.status != SessionStatus.ACTIVE,
            session_name in self.blocked_sessions,
            current_time - session.created_at > self.max_session_age,
            session.request_count >= self.max_requests_per_session,
            session.error_count >= self.max_errors_per_session
        ]
        
        if any(checks):
            session.status = SessionStatus.ROTATED
            return True
        
        return False
    
    def record_session_request(self, session_name: str, success: bool = True):
        """Record a session request."""
        if session_name in self.sessions:
            session = self.sessions[session_name]
            session.request_count += 1
            session.last_used = time.time()
            
            if not success:
                session.error_count += 1
    
    def record_session_error(self, session_name: str, error_msg: str):
        """Record a session error and potentially block the session."""
        if session_name in self.sessions:
            session = self.sessions[session_name]
            session.error_count += 1
            
            # Check for blocking conditions
            if any(keyword in error_msg.lower() for keyword in ['concurrent_access', 'session', 'blocked']):
                session.status = SessionStatus.BLOCKED
                self.blocked_sessions.add(session_name)
                print(f"🚫 Session {session_name} blocked due to: {error_msg[:100]}...")
    
    async def wait_for_request_gap(self):
        """Ensure minimum gap between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_gap:
            wait_time = self.min_request_gap - time_since_last
            await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    def get_enhanced_headers(self, site: str) -> Dict[str, str]:
        """Get enhanced headers for better scraping."""
        headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Site-specific headers
        if site == "stockx":
            headers.update({
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0',
            })
        elif site == "farfetch":
            headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Sec-Ch-Ua': '"Google Chrome";v="120", "Chromium";v="120", "Not_A Brand";v="24"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
            })
        
        return headers
    
    def _cleanup_old_sessions(self):
        """Clean up old and blocked sessions."""
        current_time = time.time()
        sessions_to_remove = []
        
        for session_name, session in self.sessions.items():
            # Remove sessions older than max age or with too many errors
            if (current_time - session.created_at > self.max_session_age or 
                session.error_count >= self.max_errors_per_session or
                session.status in [SessionStatus.BLOCKED, SessionStatus.EXPIRED]):
                sessions_to_remove.append(session_name)
        
        for session_name in sessions_to_remove:
            del self.sessions[session_name]
            self.blocked_sessions.discard(session_name)
        
        if sessions_to_remove:
            print(f"🧹 Cleaned up {len(sessions_to_remove)} old sessions")
    
    def get_session_stats(self) -> Dict[str, any]:
        """Get session statistics."""
        active_sessions = sum(1 for s in self.sessions.values() if s.status == SessionStatus.ACTIVE)
        blocked_sessions = len(self.blocked_sessions)
        total_requests = sum(s.request_count for s in self.sessions.values())
        total_errors = sum(s.error_count for s in self.sessions.values())
        
        return {
            'total_sessions': len(self.sessions),
            'active_sessions': active_sessions,
            'blocked_sessions': blocked_sessions,
            'total_requests': total_requests,
            'total_errors': total_errors,
            'error_rate': total_errors / max(total_requests, 1) * 100
        }

# Global session manager instance
session_manager = SessionManager()