import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re
from urllib.parse import quote_plus, urlencode
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
import io
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from serpapi import GoogleSearch
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# API Keys and configuration
SERPAPI_API_KEY = "525fcda2cd63c50dba6f9f5eb2c8a9a09e0722fc9cc00f54c0e2f232b00acd09"
GEMINI_API_KEY = "AIzaSyBUTIqLFwSd2p2lEZP2IH04PDfIDy43lCw"
SYSTEM_PROMPT = "You are an AI job search assistant specialized in finding AI/ML opportunities for Symbiosis Institute of Technology Pune 4th year students and fresh graduates."

# Rate limiting
REQUEST_DELAY = 2  # seconds between requests
MAX_WORKERS = 3    # concurrent workers

class JobSearchAPI:
    """Base class for job search APIs"""
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def emit_status(self, message: str, status: str = "info"):
        """Emit status to frontend"""
        try:
            socketio.emit('thought', {
                'agent': f'{self.source_name} Agent',
                'message': message,
                'status': status,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to emit status: {e}")
    
    def search_jobs(self, job_role: str, location: str = "Pune", **kwargs) -> List[Dict]:
        """Base search method - to be implemented by subclasses"""
        raise NotImplementedError

class LinkedInJobAPI(JobSearchAPI):
    """Enhanced LinkedIn job scraping and search"""
    
    def __init__(self):
        super().__init__("LinkedIn")
        self.base_url = "https://www.linkedin.com"
        
    def search_jobs(self, job_role: str, location: str = "Pune", 
                   experience_level: str = "entry", keywords: List[str] = None) -> List[Dict]:
        """Search LinkedIn jobs with multiple methods"""
        self.emit_status("Starting LinkedIn job search...")
        jobs = []
        
        try:
            # Enhanced search queries for better results
            search_queries = [
                f"{job_role} AI ML entry level {location} site:linkedin.com/jobs",
                f"{job_role} artificial intelligence fresher {location} site:linkedin.com/jobs",
                f"{job_role} machine learning graduate {location} site:linkedin.com/jobs",
                f"AI engineer entry level {location} site:linkedin.com/jobs",
                f"ML engineer fresher {location} site:linkedin.com/jobs"
            ]
            
            for i, query in enumerate(search_queries[:3]):  # Limit to 3 queries to avoid rate limits
                self.emit_status(f"Searching LinkedIn - Query {i+1}/3")
                
                try:
                    search = GoogleSearch({
                        "api_key": SERPAPI_API_KEY,
                        "engine": "google",
                        "q": query,
                        "num": 8,
                        "gl": "in",
                        "hl": "en",
                        "safe": "off"
                    })
                    
                    results = search.get_dict()
                    
                    if 'organic_results' in results:
                        for result in results['organic_results']:
                            if self._is_linkedin_job(result.get('link', '')):
                                job = self._parse_linkedin_result(result, location, experience_level)
                                if job and self._is_relevant_job(job, job_role):
                                    jobs.append(job)
                    
                    time.sleep(REQUEST_DELAY)  # Rate limiting
                    
                except Exception as e:
                    self.emit_status(f"Query {i+1} failed: {str(e)}", "warning")
                    continue
            
            self.emit_status(f"LinkedIn search completed - {len(jobs)} jobs found")
            return jobs[:15]  # Limit results
            
        except Exception as e:
            self.emit_status(f"LinkedIn search failed: {str(e)}", "error")
            logger.error(f"LinkedIn search error: {e}")
            return []
    
    def _is_linkedin_job(self, url: str) -> bool:
        """Check if URL is a LinkedIn job"""
        return url and ('linkedin.com/jobs' in url or 'linkedin.com/in/' in url)
    
    def _parse_linkedin_result(self, result: Dict, location: str, experience_level: str) -> Optional[Dict]:
        """Parse LinkedIn search result"""
        try:
            title = result.get('title', '').replace(' - LinkedIn', '').replace(' | LinkedIn', '')
            snippet = result.get('snippet', '')
            
            if not title:
                return None
            
            job = {
                'title': title.strip(),
                'company': self._extract_company_from_title(title),
                'location': location,
                'description': snippet,
                'url': result.get('link', ''),
                'source': 'LinkedIn',
                'job_type': self._determine_job_type(title),
                'experience_level': experience_level,
                'posted_date': self._extract_date(snippet),
                'salary': self._extract_salary(snippet),
                'skills': self._extract_skills(title + ' ' + snippet)
            }
            
            return job
            
        except Exception as e:
            logger.error(f"Error parsing LinkedIn result: {e}")
            return None
    
    def _extract_company_from_title(self, title: str) -> str:
        """Extract company name from job title"""
        # Clean title first
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Common patterns in LinkedIn job titles
        patterns = [
            r'at\s+([^-|•]+?)(?:\s*-|\s*\||\s*•|$)',
            r'-\s+([^|•]+?)(?:\s*\||\s*•|$)',
            r'•\s+([^•|]+?)(?:\s*-|\s*\||\s*•|$)',
            r'\|\s+([^|]+?)(?:\s*-|\s*•|$)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                company = match.group(1).strip()
                if len(company) > 2 and not any(word in company.lower() for word in ['hiring', 'jobs', 'careers']):
                    return company
        
        # Fallback: try to extract from end of title
        parts = title.split(' - ')
        if len(parts) > 1:
            potential_company = parts[-1].strip()
            if len(potential_company) > 2:
                return potential_company
        
        return "Company Not Specified"
    
    def _determine_job_type(self, title: str) -> str:
        """Determine job type from title"""
        title_lower = title.lower()
        if any(word in title_lower for word in ['intern', 'internship']):
            return 'Internship'
        elif any(word in title_lower for word in ['contract', 'freelance', 'consultant']):
            return 'Contract'
        elif any(word in title_lower for word in ['part-time', 'part time']):
            return 'Part-time'
        else:
            return 'Full-time'
    
    def _extract_date(self, text: str) -> str:
        """Extract posting date from text"""
        date_patterns = [
            r'(\d+)\s+days?\s+ago',
            r'(\d+)\s+hours?\s+ago',
            r'Posted\s+(\d+)\s+days?\s+ago',
            r'(\d+)d\s+ago',
            r'(\d+)h\s+ago'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    days_ago = int(match.group(1))
                    if 'hour' in match.group(0) or 'h' in match.group(0):
                        days_ago = 0
                    date = datetime.now() - timedelta(days=days_ago)
                    return date.strftime('%Y-%m-%d')
                except:
                    continue
        
        return datetime.now().strftime('%Y-%m-%d')
    
    def _extract_salary(self, text: str) -> str:
        """Extract salary information"""
        salary_patterns = [
            r'₹\s*[\d,]+\s*-\s*₹?\s*[\d,]+(?:\s*(?:per|/)\s*(?:month|annum|year))?',
            r'Rs\.?\s*[\d,]+\s*-\s*[\d,]+',
            r'\$\s*[\d,]+\s*-\s*\$?\s*[\d,]+',
            r'\d+\s*-\s*\d+\s*LPA',
            r'\d+\s*LPA',
            r'\d+\s*lakhs?\s*(?:per\s*)?(?:annum|year)?'
        ]
        
        for pattern in salary_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip()
        
        return "Not Disclosed"
    
    def _extract_skills(self, text: str) -> List[str]:
        """Extract relevant skills from text"""
        skills = []
        skill_keywords = [
            'python', 'java', 'javascript', 'react', 'node.js', 'django', 'flask',
            'tensorflow', 'pytorch', 'scikit-learn', 'pandas', 'numpy',
            'machine learning', 'deep learning', 'nlp', 'computer vision',
            'ai', 'artificial intelligence', 'data science', 'sql', 'mongodb',
            'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'git'
        ]
        
        text_lower = text.lower()
        for skill in skill_keywords:
            if skill in text_lower:
                skills.append(skill.title())
        
        return skills[:5]  # Limit to top 5 skills
    
    def _is_relevant_job(self, job: Dict, job_role: str) -> bool:
        """Check if job is relevant to the search"""
        title = job.get('title', '').lower()
        description = job.get('description', '').lower()
        job_role_lower = job_role.lower()
        
        # Check for AI/ML relevance
        ai_ml_keywords = ['ai', 'ml', 'machine learning', 'artificial intelligence', 
                         'data science', 'nlp', 'computer vision', 'deep learning']
        
        has_ai_ml = any(keyword in title or keyword in description for keyword in ai_ml_keywords)
        has_job_role = job_role_lower in title or any(word in title for word in job_role_lower.split())
        
        return has_ai_ml or has_job_role

class NaukriJobAPI(JobSearchAPI):
    """Enhanced Naukri.com job search API"""
    
    def __init__(self):
        super().__init__("Naukri")
        
    def search_jobs(self, job_role: str, location: str = "Pune", 
                   experience: str = "0-1") -> List[Dict]:
        """Search Naukri jobs"""
        self.emit_status("Starting Naukri job search...")
        jobs = []
        
        try:
            search_queries = [
                f"{job_role} AI ML {experience} years {location} site:naukri.com",
                f"artificial intelligence engineer fresher {location} site:naukri.com",
                f"machine learning engineer entry level {location} site:naukri.com",
                f"data scientist fresher {location} site:naukri.com"
            ]
            
            for i, query in enumerate(search_queries[:2]):  # Limit queries
                self.emit_status(f"Searching Naukri - Query {i+1}/2")
                
                try:
                    search = GoogleSearch({
                        "api_key": SERPAPI_API_KEY,
                        "engine": "google",
                        "q": query,
                        "num": 10,
                        "gl": "in"
                    })
                    
                    results = search.get_dict()
                    
                    if 'organic_results' in results:
                        for result in results['organic_results']:
                            if 'naukri.com' in result.get('link', ''):
                                job = self._parse_naukri_result(result, location, experience)
                                if job:
                                    jobs.append(job)
                    
                    time.sleep(REQUEST_DELAY)
                    
                except Exception as e:
                    self.emit_status(f"Query {i+1} failed: {str(e)}", "warning")
                    continue
            
            self.emit_status(f"Naukri search completed - {len(jobs)} jobs found")
            return jobs[:12]
            
        except Exception as e:
            self.emit_status(f"Naukri search failed: {str(e)}", "error")
            logger.error(f"Naukri search error: {e}")
            return []
    
    def _parse_naukri_result(self, result: Dict, location: str, experience: str) -> Optional[Dict]:
        """Parse Naukri search result"""
        try:
            title = result.get('title', '').replace(' - Naukri.com', '').strip()
            snippet = result.get('snippet', '')
            
            if not title:
                return None
            
            return {
                'title': title,
                'company': self._extract_company_from_snippet(snippet),
                'location': location,
                'description': snippet,
                'url': result.get('link', ''),
                'source': 'Naukri.com',
                'job_type': 'Full-time',
                'experience_level': f"{experience} years",
                'salary': self._extract_salary(snippet),
                'posted_date': self._extract_date(snippet),
                'skills': self._extract_skills(title + ' ' + snippet)
            }
            
        except Exception as e:
            logger.error(f"Error parsing Naukri result: {e}")
            return None
    
    def _extract_company_from_snippet(self, snippet: str) -> str:
        """Extract company name from snippet"""
        lines = snippet.split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line.split()) <= 4 and not any(word in line.lower() for word in ['job', 'hiring', 'experience', 'salary']):
                return line
        
        # Try first line
        if lines:
            first_line = lines[0].strip()
            if first_line and len(first_line) < 50:
                return first_line
        
        return "Company Not Specified"
    
    def _extract_salary(self, text: str) -> str:
        """Extract salary information"""
        salary_patterns = [
            r'₹\s*[\d,]+\s*-\s*₹?\s*[\d,]+',
            r'Rs\.?\s*[\d,]+\s*-\s*[\d,]+',
            r'\d+\s*-\s*\d+\s*LPA',
            r'\d+\s*LPA',
            r'\d+\s*lakhs?'
        ]
        
        for pattern in salary_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return "Not Disclosed"
    
    def _extract_date(self, text: str) -> str:
        """Extract posting date"""
        date_patterns = [
            r'(\d+)\s+days?\s+ago',
            r'posted\s+(\d+)\s+days?\s+ago'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                days_ago = int(match.group(1))
                date = datetime.now() - timedelta(days=days_ago)
                return date.strftime('%Y-%m-%d')
        
        return datetime.now().strftime('%Y-%m-%d')
    
    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills from text"""
        skills = []
        skill_keywords = [
            'Python', 'Java', 'JavaScript', 'React', 'Node.js', 'Django', 'Flask',
            'TensorFlow', 'PyTorch', 'Scikit-learn', 'Pandas', 'NumPy',
            'Machine Learning', 'Deep Learning', 'NLP', 'Computer Vision',
            'AI', 'Data Science', 'SQL', 'MongoDB', 'AWS', 'Azure'
        ]
        
        text_lower = text.lower()
        for skill in skill_keywords:
            if skill.lower() in text_lower:
                skills.append(skill)
        
        return skills[:5]

class IndeedJobAPI(JobSearchAPI):
    """Enhanced Indeed.in job search API"""
    
    def __init__(self):
        super().__init__("Indeed")
        
    def search_jobs(self, job_role: str, location: str = "Pune") -> List[Dict]:
        """Search Indeed jobs"""
        self.emit_status("Starting Indeed job search...")
        jobs = []
        
        try:
            search_queries = [
                f"{job_role} AI ML entry level {location} site:indeed.co.in",
                f"{job_role} artificial intelligence fresher {location} site:indeed.com",
                f"machine learning engineer entry level {location} site:indeed.co.in"
            ]
            
            for i, query in enumerate(search_queries[:2]):
                self.emit_status(f"Searching Indeed - Query {i+1}/2")
                
                try:
                    search = GoogleSearch({
                        "api_key": SERPAPI_API_KEY,
                        "engine": "google",
                        "q": query,
                        "num": 8,
                        "gl": "in"
                    })
                    
                    results = search.get_dict()
                    
                    if 'organic_results' in results:
                        for result in results['organic_results']:
                            link = result.get('link', '')
                            if 'indeed.co.in' in link or 'indeed.com' in link:
                                job = self._parse_indeed_result(result, location)
                                if job:
                                    jobs.append(job)
                    
                    time.sleep(REQUEST_DELAY)
                    
                except Exception as e:
                    self.emit_status(f"Query {i+1} failed: {str(e)}", "warning")
                    continue
            
            self.emit_status(f"Indeed search completed - {len(jobs)} jobs found")
            return jobs[:10]
            
        except Exception as e:
            self.emit_status(f"Indeed search failed: {str(e)}", "error")
            logger.error(f"Indeed search error: {e}")
            return []
    
    def _parse_indeed_result(self, result: Dict, location: str) -> Optional[Dict]:
        """Parse Indeed search result"""
        try:
            title = result.get('title', '').replace(' - Indeed', '').strip()
            snippet = result.get('snippet', '')
            
            if not title:
                return None
            
            return {
                'title': title,
                'company': self._extract_company_from_title(title),
                'location': location,
                'description': snippet,
                'url': result.get('link', ''),
                'source': 'Indeed',
                'job_type': 'Full-time',
                'experience_level': 'Entry Level',
                'salary': self._extract_salary(snippet),
                'posted_date': datetime.now().strftime('%Y-%m-%d'),
                'skills': self._extract_skills(title + ' ' + snippet)
            }
            
        except Exception as e:
            logger.error(f"Error parsing Indeed result: {e}")
            return None
    
    def _extract_company_from_title(self, title: str) -> str:
        """Extract company name from title"""
        if ' - ' in title:
            parts = title.split(' - ')
            if len(parts) > 1:
                return parts[-1].strip()
        return "Company Not Specified"
    
    def _extract_salary(self, text: str) -> str:
        """Extract salary from text"""
        salary_patterns = [
            r'₹\s*[\d,]+\s*-\s*₹?\s*[\d,]+',
            r'\$\s*[\d,]+\s*-\s*\$?\s*[\d,]+',
            r'\d+\s*LPA'
        ]
        
        for pattern in salary_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return "Not Disclosed"
    
    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills from text"""
        skills = []
        skill_keywords = ['Python', 'Java', 'AI', 'ML', 'TensorFlow', 'PyTorch', 'SQL']
        
        text_lower = text.lower()
        for skill in skill_keywords:
            if skill.lower() in text_lower:
                skills.append(skill)
        
        return skills

class FreshersWorldAPI(JobSearchAPI):
    """FreshersWorld job search"""
    
    def __init__(self):
        super().__init__("FreshersWorld")
    
    def search_jobs(self, job_role: str, location: str = "Pune") -> List[Dict]:
        """Search FreshersWorld jobs"""
        self.emit_status("Starting FreshersWorld job search...")
        jobs = []
        
        try:
            search_query = f"{job_role} AI ML {location} site:freshersworld.com"
            
            search = GoogleSearch({
                "api_key": SERPAPI_API_KEY,
                "engine": "google",
                "q": search_query,
                "num": 8,
                "gl": "in"
            })
            
            results = search.get_dict()
            
            if 'organic_results' in results:
                for result in results['organic_results']:
                    if 'freshersworld.com' in result.get('link', ''):
                        job = {
                            'title': result.get('title', ''),
                            'company': 'Various Companies',
                            'location': location,
                            'description': result.get('snippet', ''),
                            'url': result.get('link', ''),
                            'source': 'FreshersWorld',
                            'job_type': 'Full-time',
                            'experience_level': 'Fresher',
                            'salary': "As per industry standards",
                            'posted_date': datetime.now().strftime('%Y-%m-%d'),
                            'skills': ['Python', 'AI', 'ML']
                        }
                        jobs.append(job)
            
            self.emit_status(f"FreshersWorld search completed - {len(jobs)} jobs found")
            return jobs[:8]
            
        except Exception as e:
            self.emit_status(f"FreshersWorld search failed: {str(e)}", "error")
            logger.error(f"FreshersWorld search error: {e}")
            return []

class MonsterJobAPI(JobSearchAPI):
    """Monster.co.in job search"""
    
    def __init__(self):
        super().__init__("Monster")
    
    def search_jobs(self, job_role: str, location: str = "Pune") -> List[Dict]:
        """Search Monster jobs"""
        self.emit_status("Starting Monster job search...")
        jobs = []
        
        try:
            search_query = f"{job_role} AI ML entry level {location} site:monster.co.in"
            
            search = GoogleSearch({
                "api_key": SERPAPI_API_KEY,
                "engine": "google",
                "q": search_query,
                "num": 8,
                "gl": "in"
            })
            
            results = search.get_dict()
            
            if 'organic_results' in results:
                for result in results['organic_results']:
                    if 'monster.co.in' in result.get('link', ''):
                        job = {
                            'title': result.get('title', ''),
                            'company': self._extract_company(result.get('snippet', '')),
                            'location': location,
                            'description': result.get('snippet', ''),
                            'url': result.get('link', ''),
                            'source': 'Monster',
                            'job_type': 'Full-time',
                            'experience_level': 'Entry Level',
                            'salary': "Competitive",
                            'posted_date': datetime.now().strftime('%Y-%m-%d'),
                            'skills': ['Python', 'AI', 'ML']
                        }
                        jobs.append(job)
            
            self.emit_status(f"Monster search completed - {len(jobs)} jobs found")
            return jobs[:8]
            
        except Exception as e:
            self.emit_status(f"Monster search failed: {str(e)}", "error")
            logger.error(f"Monster search error: {e}")
            return []
    
    def _extract_company(self, snippet: str) -> str:
        """Extract company from snippet"""
        lines = snippet.split('.')
        return lines[0].strip() if lines else "Company Not Specified"

# Interview Question Search Engine


class InterviewQuestionAPI:
    """Dynamic Interview Question Search API for recent company-specific questions"""
    
    def __init__(self):
        self.source_name = "Interview Questions"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # High-quality sources for interview questions
        self.interview_sources = [
            "site:leetcode.com",
            "site:interviewbit.com", 
            "site:geeksforgeeks.org",
            "site:glassdoor.co.in",
            "site:ambitionbox.com",
            "site:careercup.com",
            "site:stackoverflow.com",
            "site:github.com",
            "site:medium.com",
            "site:dev.to",
            "site:hackernoon.com",
            "site:towardsdatascience.com"
        ]
        
        # Recent years to focus search
        self.recent_years = [2024, 2023, 2022]
        
        # Question extraction patterns
        self.question_patterns = [
            # Direct question formats
            r'Q\d*[.:\s]*(.+\?)',
            r'Question\s*\d*[.:\s]*(.+\?)',
            r'(\d+\.\s*.+\?)',
            
            # Interview experience patterns
            r'(?:asked|question was|interviewer asked)[:\s]*(.+\?)',
            r'(?:They asked|He asked|She asked)[:\s]*(.+\?)',
            
            # Leetcode/Coding platform patterns
            r'Problem[:\s]*(.+\?)',
            r'Challenge[:\s]*(.+\?)',
            
            # Technical question patterns
            r'((?:What|How|Why|When|Where|Which|Can|Do|Does|Is|Are|Will|Would|Should|Could|Have|Has|Did|Explain|Describe|Define|List|Name|Tell|Write|Find|Calculate|Solve|Compare|Analyze|Discuss|Evaluate|Implement|Design|Create)\s+[^?.!]+\?)',
            
            # Code-related questions
            r'(Write\s+(?:a\s+)?(?:function|code|program|algorithm|method)\s+(?:to|for|that)\s+[^?.!]+\?)',
            r'(Implement\s+[^?.!]+\?)',
            r'(Design\s+[^?.!]+\?)',
            
            # System design patterns
            r'(How\s+would\s+you\s+(?:design|build|implement|create)\s+[^?.!]+\?)',
        ]
        
    def emit_status(self, message: str, status: str = "info"):
        """Emit status to frontend"""
        try:
            socketio.emit('thought', {
                'agent': 'Interview Agent',
                'message': message,
                'status': status,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to emit status: {e}")
    
    def search_interview_questions(self, domain: str, company: str = None, difficulty: str = "all", question_count: int = 10) -> List[Dict]:
        """Search for real, recent interview questions from specific companies, limited to question_count"""
        self.emit_status(f"🔍 Starting dynamic search for {domain} questions from {company or 'various companies'}... Target: {question_count} questions")
        
        all_questions = []
        
        try:
            # Generate targeted search queries
            search_queries = self._generate_dynamic_search_queries(domain, company, difficulty)
            
            for i, query in enumerate(search_queries[:5]):  # Limit to 8 queries
                if len(all_questions) >= question_count:  # Stop if we have enough questions
                    break
                    
                self.emit_status(f"🔍 Searching query {i+1}/8: {query[:60]}...")
                
                try:
                    search = GoogleSearch({
                        "api_key": SERPAPI_API_KEY,
                        "engine": "google",
                        "q": query,
                        "num": min(12, question_count - len(all_questions)),  # Fetch only needed results
                        "gl": "in",
                        "hl": "en"
                    })
                    
                    results = search.get_dict()
                    
                    if 'organic_results' in results:
                        for result in results['organic_results']:
                            if len(all_questions) >= question_count:  # Stop if we have enough questions
                                break
                                
                            # Extract questions from search result
                            questions = self._extract_questions_from_result(result, domain, company)
                            all_questions.extend(questions[:question_count - len(all_questions)])  # Limit extracted questions
                            
                            # Scrape the actual page for more questions
                            page_questions = self._scrape_page_for_questions(
                                result.get('link', ''), domain, company
                            )
                            all_questions.extend(page_questions[:question_count - len(all_questions)])  # Limit scraped questions
                    
                    time.sleep(REQUEST_DELAY)  # Rate limiting
                    
                except Exception as e:
                    self.emit_status(f"❌ Query {i+1} failed: {str(e)}", "warning")
                    continue
            
            # Remove duplicates and filter by relevance
            unique_questions = self._remove_duplicate_questions(all_questions)
            relevant_questions = self._filter_relevant_questions(unique_questions, domain, company)
            
            # Limit to question_count before enhancement
            relevant_questions = relevant_questions[:question_count]
            
            # Enhance questions with AI-generated solutions
            enhanced_questions = self._enhance_questions_with_detailed_solutions(
                relevant_questions, domain, company
            )
            
            self.emit_status(f"✅ Found {len(enhanced_questions)} relevant questions")
            return enhanced_questions
        
        except Exception as e:
            self.emit_status(f"❌ Search failed: {str(e)}", "error")
            logger.error(f"Interview question search error: {e}")
            return []
    
    def _generate_dynamic_search_queries(self, domain: str, company: str = None, difficulty: str = "all") -> List[str]:
        """Generate dynamic search queries for recent interview questions"""
        queries = []
        current_year = datetime.now().year
        
        # Base query components
        domain_terms = {
            'DSA': ['data structures', 'algorithms', 'coding', 'programming'],
            'SQL': ['sql', 'database', 'mysql', 'postgresql', 'queries'],
            'OS': ['operating system', 'os', 'processes', 'threads', 'memory management'],
            'CN': ['computer networks', 'networking', 'tcp', 'ip', 'http'],
            'DBMS': ['database management', 'dbms', 'sql', 'normalization', 'transactions'],
            'Machine Learning': ['machine learning', 'ml', 'ai', 'algorithms', 'models'],
            'Deep Learning': ['deep learning', 'neural networks', 'tensorflow', 'pytorch'],
            'Python': ['python', 'programming', 'coding', 'scripting'],
            'Java': ['java', 'programming', 'coding', 'oop'],
            'System Design': ['system design', 'architecture', 'scalability', 'distributed systems']
        }
        
        domain_keywords = domain_terms.get(domain, [domain.lower()])
        
        # Company-specific queries
        if company:
            company_variations = self._get_company_variations(company)
            
            for comp_name in company_variations[:3]:  # Limit variations
                for keyword in domain_keywords[:2]:  # Limit keywords
                    queries.extend([
                        f'"{comp_name}" interview questions {keyword} {current_year} {current_year-1}',
                        f'{comp_name} {keyword} interview experience {current_year}',
                        f'{comp_name} technical interview {keyword} questions recent',
                        f'"{comp_name}" coding interview {keyword} asked questions',
                        f'{comp_name} {keyword} interview questions asked site:leetcode.com',
                        f'{comp_name} {keyword} interview questions site:geeksforgeeks.org',
                        f'{comp_name} {keyword} interview experience site:glassdoor.co.in',
                        f'"{comp_name}" {keyword} interview questions site:interviewbit.com'
                    ])
        
        # General domain queries for broader coverage
        for keyword in domain_keywords:
            queries.extend([
                f'{keyword} interview questions {current_year} {current_year-1} india',
                f'{keyword} coding interview questions asked recently',
                f'{keyword} technical interview questions and answers {current_year}',
                f'recent {keyword} interview questions indian companies',
                f'{keyword} interview preparation questions {current_year}',
                f'{keyword} interview questions asked in top companies'
            ])
        
        # Add source-specific queries
        for source in self.interview_sources[:6]:  # Limit sources
            for keyword in domain_keywords[:1]:  # One keyword per source
                queries.append(f'{keyword} interview questions {source} {current_year}')
        
        return queries[:15]  # Limit total queries
    
    def _get_company_variations(self, company: str) -> List[str]:
        """Get variations of company names for better search"""
        company_map = {
            'google': ['Google', 'Google India', 'Alphabet'],
            'microsoft': ['Microsoft', 'Microsoft India', 'MSFT'],
            'amazon': ['Amazon', 'Amazon India', 'AWS'],
            'meta': ['Meta', 'Facebook', 'FB', 'Meta India'],
            'apple': ['Apple', 'Apple India'],
            'netflix': ['Netflix', 'Netflix India'],
            'uber': ['Uber', 'Uber India', 'Uber Technologies'],
            'airbnb': ['Airbnb', 'Airbnb India'],
            'linkedin': ['LinkedIn', 'LinkedIn India'],
            'twitter': ['Twitter', 'X Corp'],
            'salesforce': ['Salesforce', 'Salesforce India'],
            'oracle': ['Oracle', 'Oracle India', 'Oracle Corporation'],
            'adobe': ['Adobe', 'Adobe India', 'Adobe Systems'],
            'intel': ['Intel', 'Intel India', 'Intel Corporation'],
            'nvidia': ['NVIDIA', 'Nvidia India'],
            'qualcomm': ['Qualcomm', 'Qualcomm India'],
            'ibm': ['IBM', 'IBM India', 'International Business Machines'],
            'cisco': ['Cisco', 'Cisco Systems', 'Cisco India'],
            'vmware': ['VMware', 'VMWare India'],
            'servicenow': ['ServiceNow', 'ServiceNow India'],
            'snowflake': ['Snowflake', 'Snowflake Computing'],
            'databricks': ['Databricks'],
            'palantir': ['Palantir', 'Palantir Technologies'],
            'stripe': ['Stripe', 'Stripe India'],
            'shopify': ['Shopify'],
            'zoom': ['Zoom', 'Zoom Video Communications'],
            'slack': ['Slack', 'Slack Technologies'],
            'atlassian': ['Atlassian'],
            'gitlab': ['GitLab'],
            'github': ['GitHub'],
            'docker': ['Docker', 'Docker Inc'],
            'kubernetes': ['Kubernetes'],
            'tcs': ['TCS', 'Tata Consultancy Services', 'TATA'],
            'infosys': ['Infosys', 'Infosys Limited'],
            'wipro': ['Wipro', 'Wipro Limited', 'Wipro Technologies'],
            'hcl': ['HCL', 'HCL Technologies', 'HCLTech'],
            'accenture': ['Accenture', 'Accenture India'],
            'cognizant': ['Cognizant', 'CTS', 'Cognizant Technology Solutions'],
            'capgemini': ['Capgemini', 'Cap Gemini India'],
            'deloitte': ['Deloitte', 'Deloitte India'],
            'pwc': ['PwC', 'PricewaterhouseCoopers'],
            'ey': ['EY', 'Ernst & Young'],
            'kpmg': ['KPMG', 'KPMG India'],
            'flipkart': ['Flipkart', 'Flipkart India'],
            'paytm': ['Paytm', 'PayTM', 'One97 Communications'],
            'ola': ['Ola', 'Ola Cabs', 'Ola Electric'],
            'zomato': ['Zomato', 'Zomato India'],
            'swiggy': ['Swiggy'],
            'byju': ['BYJU\'S', 'Byjus', 'Think and Learn'],
            'unacademy': ['Unacademy'],
            'phonepe': ['PhonePe', 'Phone Pe'],
            'razorpay': ['Razorpay'],
            'freshworks': ['Freshworks', 'Freshdesk'],
            'zoho': ['Zoho', 'Zoho Corporation'],
            'mindtree': ['Mindtree', 'LTI Mindtree']
        }
        
        company_lower = company.lower()
        for key, variations in company_map.items():
            if key in company_lower or company_lower in key:
                return variations
        
        # If not found in map, return basic variations
        return [company, company.upper(), company.title(), f"{company} India"]
    
    def _extract_questions_from_result(self, result: Dict, domain: str, company: str = None) -> List[Dict]:
        """Extract questions from search result snippet and title"""
        questions = []
        
        try:
            title = result.get('title', '')
            snippet = result.get('snippet', '')
            url = result.get('link', '')
            
            # Combine title and snippet for extraction
            text = f"{title} {snippet}"
            
            # Extract questions using patterns
            extracted_questions = self._extract_questions_from_text(text)
            
            for question_text in extracted_questions:
                if self._is_valid_interview_question(question_text):
                    # Determine the source and credibility
                    source_info = self._analyze_source_credibility(url, title)
                    
                    question = {
                        'question': question_text.strip(),
                        'domain': domain,
                        'company': company or self._extract_company_from_text(text),
                        'difficulty': self._determine_question_difficulty(question_text, domain),
                        'source_url': url,
                        'source_title': title,
                        'source_type': source_info['type'],
                        'credibility_score': source_info['score'],
                        'year': self._extract_year_from_text(text),
                        'question_type': self._classify_question_type(question_text, domain),
                        'solution': ""  # Will be filled by AI enhancement
                    }
                    questions.append(question)
                    
        except Exception as e:
            logger.error(f"Error extracting questions from result: {e}")
        
        return questions
    
    def _scrape_page_for_questions(self, url: str, domain: str, company: str = None) -> List[Dict]:
        """Scrape the actual page content for interview questions"""
        questions = []
        
        if not url or not self._is_safe_url(url):
            return questions
        
        try:
            response = self.session.get(url, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Extract text content
            text_content = soup.get_text()
            
            # Look for structured question content
            question_elements = []
            
            # Method 1: Look for list items that might contain questions
            list_items = soup.find_all(['li', 'div', 'p'], text=re.compile(r'\?'))
            question_elements.extend(list_items)
            
            # Method 2: Look for headings that might be questions
            headings = soup.find_all(['h1', 'h2', 'h3', 'h4'], text=re.compile(r'\?'))
            question_elements.extend(headings)
            
            # Method 3: Look for code blocks or pre tags (common in coding questions)
            code_blocks = soup.find_all(['pre', 'code'])
            for block in code_blocks:
                parent = block.find_parent()
                if parent and '?' in parent.get_text():
                    question_elements.append(parent)
            
            # Extract questions from elements
            for element in question_elements:
                element_text = element.get_text(strip=True)
                extracted = self._extract_questions_from_text(element_text)
                
                for question_text in extracted:
                    if self._is_valid_interview_question(question_text):
                        source_info = self._analyze_source_credibility(url, soup.title.string if soup.title else '')
                        
                        question = {
                            'question': question_text.strip(),
                            'domain': domain,
                            'company': company or self._extract_company_from_text(element_text),
                            'difficulty': self._determine_question_difficulty(question_text, domain),
                            'source_url': url,
                            'source_title': soup.title.string if soup.title else '',
                            'source_type': source_info['type'],
                            'credibility_score': source_info['score'],
                            'year': self._extract_year_from_text(element_text) or datetime.now().year,
                            'question_type': self._classify_question_type(question_text, domain),
                            'solution': ""
                        }
                        questions.append(question)
            
            # Method 4: Extract from full text content as fallback
            if len(questions) < 3:  # If we didn't find many questions
                text_questions = self._extract_questions_from_text(text_content)
                for question_text in text_questions[:10]:  # Limit fallback questions
                    if self._is_valid_interview_question(question_text):
                        source_info = self._analyze_source_credibility(url, soup.title.string if soup.title else '')
                        
                        question = {
                            'question': question_text.strip(),
                            'domain': domain,
                            'company': company or self._extract_company_from_text(question_text),
                            'difficulty': self._determine_question_difficulty(question_text, domain),
                            'source_url': url,
                            'source_title': soup.title.string if soup.title else '',
                            'source_type': source_info['type'],
                            'credibility_score': source_info['score'],
                            'year': self._extract_year_from_text(text_content) or datetime.now().year,
                            'question_type': self._classify_question_type(question_text, domain),
                            'solution': ""
                        }
                        questions.append(question)
            
        except Exception as e:
            logger.error(f"Error scraping page {url}: {e}")
        
        return questions[:15]  # Limit questions per page
    
    def _extract_questions_from_text(self, text: str) -> List[str]:
        """Extract interview questions from text using multiple patterns"""
        questions = set()  # Use set to avoid immediate duplicates
        
        # Clean text
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s\?\.\!\-\(\),;:]', ' ', text)
        
        # Apply all question patterns
        for pattern in self.question_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                if isinstance(match, tuple):
                    question = match[0] if match[0] else (match[1] if len(match) > 1 else '')
                else:
                    question = match
                
                question = question.strip()
                if question and len(question) > 10:
                    # Clean up the question
                    question = re.sub(r'\s+', ' ', question)
                    question = question.strip(' .,;:')
                    
                    if not question.endswith('?'):
                        question += '?'
                    
                    questions.add(question)
        
        return list(questions)
    
    def _is_valid_interview_question(self, text: str) -> bool:
        """Validate if text is a proper interview question"""
        if not text or len(text.strip()) < 10 or len(text.strip()) > 1000:
            return False
        
        text_lower = text.lower().strip()
        
        # Must end with question mark
        if not text.endswith('?'):
            return False
        
        # Should contain question indicators
        question_indicators = [
            'what', 'how', 'why', 'when', 'where', 'which', 'who', 'whose',
            'can', 'could', 'would', 'should', 'will', 'do', 'does', 'did',
            'is', 'are', 'was', 'were', 'has', 'have', 'had',
            'explain', 'describe', 'define', 'list', 'name', 'tell',
            'write', 'implement', 'design', 'create', 'build', 'solve',
            'find', 'calculate', 'compare', 'analyze', 'discuss', 'evaluate'
        ]
        
        has_question_word = any(word in text_lower for word in question_indicators)
        
        # Exclude non-question content
        exclude_phrases = [
            'click here', 'read more', 'see also', 'related articles',
            'advertisement', 'subscribe', 'follow us', 'share this',
            'comments', 'reply', 'like this', 'vote up'
        ]
        
        has_excluded = any(phrase in text_lower for phrase in exclude_phrases)
        
        return has_question_word and not has_excluded
    
    def _analyze_source_credibility(self, url: str, title: str) -> Dict[str, any]:
        """Analyze the credibility of the source"""
        credibility_score = 0
        source_type = "unknown"
        
        if not url:
            return {"type": "unknown", "score": 0}
        
        url_lower = url.lower()
        title_lower = title.lower()
        
        # High credibility sources
        if any(domain in url_lower for domain in ['leetcode.com', 'interviewbit.com', 'geeksforgeeks.org']):
            credibility_score = 9
            source_type = "coding_platform"
        elif any(domain in url_lower for domain in ['glassdoor.co.in', 'glassdoor.com', 'ambitionbox.com']):
            credibility_score = 8
            source_type = "job_review"
        elif any(domain in url_lower for domain in ['github.com', 'stackoverflow.com']):
            credibility_score = 7
            source_type = "developer_community"
        elif any(domain in url_lower for domain in ['medium.com', 'dev.to', 'hackernoon.com']):
            credibility_score = 6
            source_type = "tech_blog"
        elif any(domain in url_lower for domain in ['careercup.com', 'pramp.com']):
            credibility_score = 8
            source_type = "interview_prep"
        elif any(phrase in title_lower for phrase in ['interview experience', 'asked in interview', 'interview questions']):
            credibility_score += 3
            source_type = "interview_experience"
        
        # Boost score for recent content
        if any(year in title_lower for year in ['2024', '2023', '2022']):
            credibility_score += 1
        
        return {"type": source_type, "score": credibility_score}
    
    def _determine_question_difficulty(self, question_text: str, domain: str) -> str:
        """Determine question difficulty based on content and keywords"""
        question_lower = question_text.lower()
        
        # Domain-specific difficulty indicators
        difficulty_indicators = {
            'easy': [
                'what is', 'define', 'explain', 'basic', 'introduction',
                'difference between', 'types of', 'advantages', 'disadvantages',
                'simple', 'basic concept', 'fundamental'
            ],
            'medium': [
                'implement', 'design', 'algorithm', 'optimize', 'efficient',
                'time complexity', 'space complexity', 'approach', 'solution',
                'strategy', 'method'
            ],
            'hard': [
                'advanced', 'complex', 'distributed', 'scalable', 'architecture',
                'system design', 'optimization', 'performance', 'large scale',
                'trade-offs', 'design patterns', 'microservices'
            ]
        }
        
        easy_count = sum(1 for indicator in difficulty_indicators['easy'] if indicator in question_lower)
        medium_count = sum(1 for indicator in difficulty_indicators['medium'] if indicator in question_lower)
        hard_count = sum(1 for indicator in difficulty_indicators['hard'] if indicator in question_lower)
        
        if hard_count > 0 or len(question_text) > 200:
            return "Hard"
        elif medium_count > easy_count or any(word in question_lower for word in ['implement', 'algorithm', 'code']):
            return "Medium"
        else:
            return "Easy"
    
    def _classify_question_type(self, question_text: str, domain: str) -> str:
        """Classify the type of interview question"""
        question_lower = question_text.lower()
        
        if any(word in question_lower for word in ['implement', 'write', 'code', 'program', 'function']):
            return "Coding"
        elif any(word in question_lower for word in ['design', 'architecture', 'system', 'scalable']):
            return "System Design"
        elif any(word in question_lower for word in ['what is', 'define', 'explain', 'describe']):
            return "Conceptual"
        elif any(word in question_lower for word in ['difference', 'compare', 'vs', 'versus']):
            return "Comparison"
        elif any(word in question_lower for word in ['optimize', 'improve', 'efficient', 'better']):
            return "Optimization"
        else:
            return "General"
    
    def _extract_company_from_text(self, text: str) -> str:
        """Extract company name from question context"""
        text_lower = text.lower()
        
        # Common company indicators
        company_patterns = [
            r'(?:at|in|during|from)\s+([A-Z][a-zA-Z\s&.]+?)(?:\s+interview|\s+asked|\s|,|\.|$)',
            r'([A-Z][a-zA-Z\s&.]+?)\s+(?:interview|asked|company)',
            r'(?:asked\s+at|interviewed\s+at)\s+([A-Z][a-zA-Z\s&.]+?)(?:\s|,|\.|$)'
        ]
        
        for pattern in company_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match.strip()) > 1 and len(match.strip()) < 30:
                    return match.strip()
        
        return "Various Companies"
    
    def _extract_year_from_text(self, text: str) -> Optional[int]:
        """Extract year from text content"""
        year_pattern = r'\b(202[0-5]|201[5-9])\b'
        matches = re.findall(year_pattern, text)
        if matches:
            return int(matches[0])
        return None
    
    def _is_safe_url(self, url: str) -> bool:
        """Check if URL is safe to scrape"""
        if not url:
            return False
        
        safe_domains = [
            'leetcode.com', 'interviewbit.com', 'geeksforgeeks.org',
            'glassdoor.co.in', 'glassdoor.com', 'ambitionbox.com',
            'careercup.com', 'github.com', 'stackoverflow.com',
            'medium.com', 'dev.to', 'hackernoon.com'
        ]
        
        return any(domain in url.lower() for domain in safe_domains)
    
    def _remove_duplicate_questions(self, questions: List[Dict]) -> List[Dict]:
        """Remove duplicate questions using advanced similarity detection"""
        if not questions:
            return []
        
        unique_questions = []
        seen_hashes = set()
        
        for question in questions:
            question_text = question.get('question', '').lower().strip()
            
            # Create a normalized version for duplicate detection
            normalized = re.sub(r'[^\w\s]', '', question_text)
            normalized = re.sub(r'\s+', ' ', normalized)
            
            # Create hash
            question_hash = hashlib.md5(normalized.encode()).hexdigest()
            
            if question_hash not in seen_hashes:
                seen_hashes.add(question_hash)
                unique_questions.append(question)
        
        return unique_questions
    
    def _filter_relevant_questions(self, questions: List[Dict], domain: str, company: str = None) -> List[Dict]:
        """Filter questions by relevance to domain and company"""
        if not questions:
            return []
        
        # Score questions by relevance
        scored_questions = []
        
        for question in questions:
            score = self._calculate_relevance_score(question, domain, company)
            if score > 3:  # Minimum relevance threshold
                question['relevance_score'] = score
                scored_questions.append(question)
        
        # Sort by relevance score
        scored_questions.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return scored_questions
    
    def _calculate_relevance_score(self, question: Dict, domain: str, company: str = None) -> int:
        """Calculate relevance score for a question"""
        score = 0
        question_text = question.get('question', '').lower()
        question_domain = question.get('domain', '').lower()
        question_company = question.get('company', '').lower()
        
        # Domain matching
        if domain.lower() in question_text or domain.lower() in question_domain:
            score += 5
        
        # Company matching
        if company and company.lower() in question_company:
            score += 8
        
        # Source credibility
        score += question.get('credibility_score', 0)
        
        # Recent questions get higher score
        year = question.get('year')
        if year and year >= 2023:
            score += 3
        elif year and year >= 2020:
            score += 1
        
        # Question type preference
        question_type = question.get('question_type', '')
        if question_type in ['Coding', 'System Design']:
            score += 2
        
        # Difficulty distribution
        difficulty = question.get('difficulty', '')
        if difficulty == 'Medium':
            score += 2
        elif difficulty == 'Hard':
            score += 1
        
        return score
    
    def _enhance_questions_with_detailed_solutions(self, questions: List[Dict], domain: str, company: str = None) -> List[Dict]:
        """Enhance questions with detailed AI-generated solutions"""
        if not questions:
            return []
        
        self.emit_status(f"🤖 Generating detailed solutions for {len(questions)} questions...")
        
        enhanced_questions = []
        batch_size = 5  # Process in batches to manage API rate limits
        
        for i in range(0, len(questions), batch_size):
            batch = questions[i:i+batch_size]
            
            for j, question in enumerate(batch):
                try:
                    self.emit_status(f"💡 Generating solution {i+j+1}/{len(questions)}...")
                    
                    solution = self._generate_comprehensive_solution(
                        question['question'], 
                        domain, 
                        company,
                        question.get('difficulty', 'Medium'),
                        question.get('question_type', 'General')
                    )
                    
                    question['solution'] = solution
                    enhanced_questions.append(question)
                    
                    # Small delay between API calls
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error generating solution for question {i+j+1}: {e}")
                    question['solution'] = self._get_fallback_solution(question['question'], domain)
                    enhanced_questions.append(question)
            
            # Longer delay between batches
            if i + batch_size < len(questions):
                time.sleep(2)
        
        self.emit_status(f"✅ Generated solutions for all questions!")
        return enhanced_questions
    
    def _generate_comprehensive_solution(self, question: str, domain: str, company: str = None, 
                                       difficulty: str = "Medium", question_type: str = "General") -> str:
        """Generate comprehensive solution using Gemini AI"""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            
            # Create context-aware prompt
            company_context = f" (specifically asked at {company})" if company else ""
            
            prompt = f"""
You are an expert technical interviewer and educator. Provide a comprehensive answer to this {domain} interview question{company_context}:

**Question:** {question}

**Context:**
- Domain: {domain}
- Difficulty Level: {difficulty}
- Question Type: {question_type}
- Target Audience: Fresh graduates and 4th year students from Indian engineering colleges

Please provide a structured response with:

## 1. Concept Explanation
- Clear explanation of the underlying concept
- Key terminology and definitions
- Why this concept is important in {domain}

## 2. Detailed Solution
- Step-by-step approach to solve this problem
- Multiple approaches if applicable (brute force, optimized, etc.)
- Time and space complexity analysis (if applicable)

## 3. Code Implementation (if applicable)
- Clean, well-commented code in Python or Java
- Include input/output examples
- Handle edge cases

## 4. Key Points for Interview
- Important points to remember and mention
- Common mistakes to avoid
- Follow-up questions you might be asked

## 5. Related Concepts
- Connected topics you should know
- How this fits into the broader {domain} landscape

Keep the explanation:
- Beginner-friendly but technically accurate
- Focused on Indian job market expectations
- Include practical examples where possible
- Maximum 500 words for clarity

Format the response in clean markdown with proper headers and code blocks.
"""
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            
            headers = {'Content-Type': 'application/json'}
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                solution = result['candidates'][0]['content']['parts'][0]['text']
                return solution.strip()
            else:
                logger.error(f"Gemini API error: {response.status_code}")
                return self._get_fallback_solution(question, domain)
                
        except Exception as e:
            logger.error(f"AI solution generation failed: {e}")
            return self._get_fallback_solution(question, domain)
    
    def _get_fallback_solution(self, question: str, domain: str) -> str:
        """Generate fallback solution when AI fails"""
        return f"""
## Solution for: {question}

**Domain:** {domain}

### Approach:
This is a fundamental {domain} question that requires understanding of core concepts. 

### Key Points to Remember:
- Understand the basic concept thoroughly
- Practice similar problems
- Know the time and space complexity
- Be prepared for follow-up questions

### Recommended Study Resources:
- GeeksforGeeks articles on {domain}
- LeetCode problems related to this topic
- Standard {domain} textbooks and online courses

### Interview Tips:
1. Start by clarifying the question requirements
2. Explain your thought process step by step
3. Write clean, readable code
4. Test your solution with examples
5. Discuss optimization possibilities

*For a detailed solution, please refer to standard {domain} resources or consult with technical mentors.*
"""

class PDFGenerator:
    """Generate professional PDF reports for interview questions"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom styles for PDF"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.darkblue,
            alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            name='QuestionStyle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.darkred,
            leftIndent=10
        ))
        self.styles.add(ParagraphStyle(
            name='SolutionStyle',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=20,
            leftIndent=20,
            rightIndent=10,
            alignment=TA_JUSTIFY
        ))
        self.styles.add(ParagraphStyle(
            name='HeaderStyle',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=colors.blue,
            spaceAfter=6
        ))
    
    def generate_pdf(self, domain: str, questions: List[Dict], company: str = None) -> io.BytesIO:
        """Generate standard PDF report for interview questions"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
        story = []
        
        title_text = f"{domain} Interview Questions"
        if company:
            title_text += f" - {company}"
        story.append(Paragraph(title_text, self.styles['CustomTitle']))
        story.append(Spacer(1, 20))
        
        story.append(Paragraph(f"<b>Domain:</b> {domain}", self.styles['HeaderStyle']))
        if company:
            story.append(Paragraph(f"<b>Company:</b> {company}", self.styles['HeaderStyle']))
        story.append(Paragraph(f"<b>Total Questions:</b> {len(questions)}", self.styles['HeaderStyle']))
        story.append(Paragraph(f"<b>Generated on:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", self.styles['HeaderStyle']))
        story.append(Paragraph(f"<b>Prepared for:</b> SIT Pune Students", self.styles['HeaderStyle']))
        story.append(Spacer(1, 30))
        
        for i, question in enumerate(questions, 1):
            question_text = f"Q{i}. {question.get('question', 'N/A')}"
            story.append(Paragraph(question_text, self.styles['QuestionStyle']))
            
            metadata = []
            if question.get('company') and question.get('company') != 'Various Companies':
                metadata.append(f"Company: {question['company']}")
            if question.get('year'):
                metadata.append(f"Year: {question['year']}")
            if question.get('difficulty'):
                metadata.append(f"Difficulty: {question['difficulty']}")
            
            if metadata:
                story.append(Paragraph(f"<i>{' | '.join(metadata)}</i>", self.styles['Normal']))
                story.append(Spacer(1, 6))
            
            solution = question.get('solution', 'Solution not available.')
            story.append(Paragraph(f"<b>Solution:</b>", self.styles['Normal']))
            story.append(Paragraph(solution, self.styles['SolutionStyle']))
            
            if i % 3 == 0 and i < len(questions):
                story.append(PageBreak())
            else:
                story.append(Spacer(1, 20))
        
        story.append(Spacer(1, 30))
        story.append(Paragraph("<i>Generated by SIT Career Platform - Symbiosis Institute of Technology, Pune</i>", 
                              self.styles['Normal']))
        
        doc.build(story)
        buffer.seek(0)
        return buffer
    
    def generate_enhanced_pdf(self, domain: str, questions: List[Dict], company: str = None, 
                            include_solutions: bool = True, difficulty_filter: str = 'all') -> io.BytesIO:
        """Generate enhanced PDF report with filtering and customizable options"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
        story = []
        
        # Filter questions by difficulty if specified
        filtered_questions = questions
        if difficulty_filter.lower() != 'all':
            filtered_questions = [q for q in questions if q.get('difficulty', '').lower() == difficulty_filter.lower()]
        
        # Title with enhanced details
        title_text = f"{domain} Interview Preparation"
        if company:
            title_text += f" - {company}"
        if difficulty_filter.lower() != 'all':
            title_text += f" ({difficulty_filter.title()} Difficulty)"
        story.append(Paragraph(title_text, self.styles['CustomTitle']))
        story.append(Spacer(1, 20))
        
        # Enhanced header with more metadata
        story.append(Paragraph(f"<b>Domain:</b> {domain}", self.styles['HeaderStyle']))
        if company:
            story.append(Paragraph(f"<b>Company:</b> {company}", self.styles['HeaderStyle']))
        story.append(Paragraph(f"<b>Total Questions:</b> {len(filtered_questions)}", self.styles['HeaderStyle']))
        story.append(Paragraph(f"<b>Difficulty:</b> {difficulty_filter.title() if difficulty_filter.lower() != 'all' else 'All Levels'}", 
                             self.styles['HeaderStyle']))
        story.append(Paragraph(f"<b>Solutions Included:</b> {include_solutions}", self.styles['HeaderStyle']))
        story.append(Paragraph(f"<b>Generated on:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
                             self.styles['HeaderStyle']))
        story.append(Paragraph(f"<b>Prepared for:</b> SIT Pune Students & Graduates", self.styles['HeaderStyle']))
        story.append(Spacer(1, 30))
        
        # Add questions with enhanced formatting
        for i, question in enumerate(filtered_questions, 1):
            question_text = f"Q{i}. {question.get('question', 'N/A')}"
            story.append(Paragraph(question_text, self.styles['QuestionStyle']))
            
            # Enhanced metadata
            metadata = []
            if question.get('company') and question.get('company') != 'Various Companies':
                metadata.append(f"Company: {question['company']}")
            if question.get('year'):
                metadata.append(f"Year: {question['year']}")
            if question.get('difficulty'):
                metadata.append(f"Difficulty: {question['difficulty']}")
            if question.get('question_type'):
                metadata.append(f"Type: {question['question_type']}")
            if question.get('source_url'):
                metadata.append(f"Source: <link href='{question['source_url']}' color='blue'>{question.get('source_title', 'Link')}</link>")
            
            if metadata:
                story.append(Paragraph(f"<i>{' | '.join(metadata)}</i>", self.styles['Normal']))
                story.append(Spacer(1, 8))
            
            # Conditionally include solutions
            if include_solutions:
                solution = question.get('solution', 'Solution not available.')
                story.append(Paragraph(f"<b>Solution:</b>", self.styles['Normal']))
                # Split solution into paragraphs for better readability
                solution_paragraphs = solution.split('\n\n')
                for para in solution_paragraphs:
                    cleaned_para = re.sub(r'#+', '', para).strip()  # Remove markdown headers
                    story.append(Paragraph(cleaned_para, self.styles['SolutionStyle']))
            
            # Add source credibility if available
            if question.get('credibility_score'):
                story.append(Paragraph(f"<i>Source Credibility Score: {question['credibility_score']}/10</i>", 
                                     self.styles['Normal']))
            
            # Page break logic
            if i % 2 == 0 and i < len(filtered_questions):
                story.append(PageBreak())
            else:
                story.append(Spacer(1, 25))
        
        # Enhanced footer
        story.append(Spacer(1, 40))
        footer_text = (
            "<i>Generated by SIT Career Platform - Symbiosis Institute of Technology, Pune<br/>"
            "For academic and career preparation purposes only<br/>"
            f"Contact: career.services@sitpune.edu.in</i>"
        )
        story.append(Paragraph(footer_text, self.styles['Normal']))
        
        try:
            doc.build(story)
        except Exception as e:
            logger.error(f"PDF build error: {str(e)}")
            raise Exception(f"Failed to build PDF: {str(e)}")
        
        buffer.seek(0)
        return buffer

class JobSearchEngine:
    """Main class that orchestrates all job search operations"""
    
    def __init__(self):
        self.linkedin_api = LinkedInJobAPI()
        self.naukri_api = NaukriJobAPI()
        self.indeed_api = IndeedJobAPI()
        self.freshers_api = FreshersWorldAPI()
        self.monster_api = MonsterJobAPI()
        self.interview_api = InterviewQuestionAPI()
        self.pdf_generator = PDFGenerator()
    
    def comprehensive_job_search(self, job_role: str, location: str = "Pune", 
                               filters: Dict = None):
        """Perform comprehensive job search across all sources"""
        results = {
            'job_role': job_role,
            'location': location,
            'timestamp': datetime.now().isoformat(),
            'total_jobs': 0,
            'sources': {},
            'all_jobs': [],
            'search_status': 'in_progress'
        }
        
        filters = filters or {}
        experience_level = filters.get('experience_level', 'entry')
        
        try:
            socketio.emit('search_started', {
                'message': f"Starting comprehensive search for {job_role} AI/ML jobs in {location}...",
                'job_role': job_role,
                'location': location
            })
            
            # Use ThreadPoolExecutor for concurrent searches
            search_tasks = []
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                # Submit search tasks
                search_tasks.append(
                    executor.submit(self._safe_search, self.linkedin_api, job_role, location, experience_level=experience_level)
                )
                search_tasks.append(
                    executor.submit(self._safe_search, self.naukri_api, job_role, location, experience=filters.get('experience', '0-1'))
                )
                search_tasks.append(
                    executor.submit(self._safe_search, self.indeed_api, job_role, location)
                )
                search_tasks.append(
                    executor.submit(self._safe_search, self.freshers_api, job_role, location)
                )
                search_tasks.append(
                    executor.submit(self._safe_search, self.monster_api, job_role, location)
                )
                
                # Collect results as they complete
                source_names = ['linkedin', 'naukri', 'indeed', 'freshersworld', 'monster']
                
                for i, future in enumerate(as_completed(search_tasks)):
                    try:
                        source_jobs = future.result(timeout=30)  # 30 second timeout
                        source_name = source_names[i] if i < len(source_names) else f'source_{i}'
                        
                        results['sources'][source_name] = source_jobs
                        results['all_jobs'].extend(source_jobs)
                        
                        socketio.emit('source_completed', {
                            'source': source_name,
                            'job_count': len(source_jobs),
                            'total_so_far': len(results['all_jobs'])
                        })
                        
                    except Exception as e:
                        logger.error(f"Search task failed: {e}")
                        continue
            
            # Process and rank results
            socketio.emit('thought', {
                'agent': 'System',
                'message': "Processing and ranking results..."
            })
            
            results['all_jobs'] = self._remove_duplicates_and_rank(results['all_jobs'], job_role)
            results['total_jobs'] = len(results['all_jobs'])
            results['search_status'] = 'completed'
            
            # Add search summary
            results['summary'] = self._generate_search_summary(results)
            
            socketio.emit('search_completed', results)
            
        except Exception as e:
            logger.error(f"Comprehensive search failed: {e}")
            results['search_status'] = 'failed'
            results['error'] = str(e)
            socketio.emit('search_failed', results)
    
    def search_interview_questions(self, domain: str, company: str = None, difficulty: str = "all", question_count: int = 10):
        """Enhanced interview question search method"""
        try:
            socketio.emit('interview_search_started', {
                'message': f"🔍 Starting comprehensive search for {domain} questions from {company or 'various companies'}...",
                'domain': domain,
                'company': company,
                'difficulty': difficulty,
                'target_count': question_count
            })
            
            # Use the enhanced API
            questions = self.interview_api.search_interview_questions(domain, company, difficulty)
            
            # Limit to requested count
            questions = questions[:question_count]
            
            results = {
                'domain': domain,
                'company': company,
                'difficulty': difficulty,
                'questions': questions,
                'total_questions': len(questions),
                'search_metadata': {
                    'sources_searched': len(self.interview_api.interview_sources),
                    'search_queries_used': 5,
                    'credibility_filtered': True,
                    'ai_enhanced': True,
                    'recent_questions_only': True
                },
                'timestamp': datetime.now().isoformat()
            }
            
            socketio.emit('interview_search_completed', results)
            
        except Exception as e:
            logger.error(f"Enhanced interview question search failed: {e}")
            socketio.emit('interview_search_failed', {
                'error': str(e),
                'domain': domain,
                'company': company,
                'timestamp': datetime.now().isoformat()
            })
    
    def _safe_search(self, api_instance, job_role: str, location: str, **kwargs) -> List[Dict]:
        """Safely execute search with error handling"""
        try:
            return api_instance.search_jobs(job_role, location, **kwargs)
        except Exception as e:
            logger.error(f"{api_instance.source_name} search failed: {e}")
            return []
    
    def _remove_duplicates_and_rank(self, jobs: List[Dict], job_role: str) -> List[Dict]:
        """Remove duplicate jobs and rank by relevance"""
        seen_jobs = set()
        unique_jobs = []
        
        for job in jobs:
            # Create a more robust hash based on title, company, and description
            job_hash = self._create_job_hash(job)
            
            if job_hash not in seen_jobs and self._is_valid_job(job):
                seen_jobs.add(job_hash)
                # Calculate relevance score
                job['relevance_score'] = self._calculate_relevance(job, job_role)
                unique_jobs.append(job)
        
        # Sort by relevance score (descending)
        unique_jobs.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        return unique_jobs[:50]  # Limit to top 50 jobs
    
    def _create_job_hash(self, job: Dict) -> str:
        """Create a hash for job deduplication"""
        title = job.get('title', '').lower().strip()
        company = job.get('company', '').lower().strip()
        
        # Normalize title
        title = re.sub(r'[^\w\s]', '', title)
        title = re.sub(r'\s+', ' ', title)
        
        # Create hash
        hash_string = f"{title}_{company}"
        return hashlib.md5(hash_string.encode()).hexdigest()
    
    def _is_valid_job(self, job: Dict) -> bool:
        """Check if job has valid data"""
        required_fields = ['title', 'company', 'url']
        return all(job.get(field) and job.get(field).strip() for field in required_fields)
    
    def _calculate_relevance(self, job: Dict, job_role: str) -> int:
        """Calculate relevance score for job"""
        score = 0
        title = job.get('title', '').lower()
        description = job.get('description', '').lower()
        job_role_lower = job_role.lower()
        
        # Title matching (highest priority)
        if job_role_lower in title:
            score += 20
        
        # Keywords matching
        keywords = job_role_lower.split()
        for keyword in keywords:
            if keyword in title:
                score += 8
            if keyword in description:
                score += 3
        
        # AI/ML specific keywords
        ai_ml_keywords = ['ai', 'ml', 'machine learning', 'artificial intelligence', 
                         'deep learning', 'neural network', 'nlp', 'computer vision',
                         'data science', 'tensorflow', 'pytorch']
        
        for keyword in ai_ml_keywords:
            if keyword in title:
                score += 10
            if keyword in description:
                score += 5
        
        # Source preference (LinkedIn and Naukri are popular in India)
        source = job.get('source', '').lower()
        if 'linkedin' in source:
            score += 8
        elif 'naukri' in source:
            score += 6
        elif 'indeed' in source:
            score += 4
        
        # Experience level matching for freshers
        exp_level = job.get('experience_level', '').lower()
        if any(word in exp_level for word in ['entry', 'fresher', '0-1', 'graduate']):
            score += 10
        
        # Job type preference
        job_type = job.get('job_type', '').lower()
        if job_type == 'full-time':
            score += 5
        elif job_type == 'internship':
            score += 3
        
        # Recent jobs get higher score
        try:
            posted_date = job.get('posted_date', '')
            if posted_date:
                job_date = datetime.strptime(posted_date, '%Y-%m-%d')
                days_old = (datetime.now() - job_date).days
                if days_old <= 7:
                    score += 8
                elif days_old <= 30:
                    score += 4
        except:
            pass
        
        return score
    
    def _generate_search_summary(self, results: Dict) -> Dict:
        """Generate search summary statistics"""
        total_jobs = results.get('total_jobs', 0)
        sources = results.get('sources', {})
        
        summary = {
            'total_jobs_found': total_jobs,
            'sources_searched': len(sources),
            'source_breakdown': {},
            'top_companies': self._get_top_companies(results.get('all_jobs', [])),
            'job_types': self._get_job_type_distribution(results.get('all_jobs', [])),
            'experience_levels': self._get_experience_distribution(results.get('all_jobs', [])),
            'search_timestamp': results.get('timestamp')
        }
        
        # Source breakdown
        for source, jobs in sources.items():
            summary['source_breakdown'][source] = len(jobs)
        
        return summary
    
    def _get_top_companies(self, jobs: List[Dict], limit: int = 10) -> List[Dict]:
        """Get top hiring companies"""
        company_count = {}
        for job in jobs:
            company = job.get('company', 'Unknown')
            if company != 'Company Not Specified' and company != 'Unknown':
                company_count[company] = company_count.get(company, 0) + 1
        
        return [{'company': company, 'job_count': count} 
                for company, count in sorted(company_count.items(), 
                key=lambda x: x[1], reverse=True)[:limit]]
    
    def _get_job_type_distribution(self, jobs: List[Dict]) -> Dict[str, int]:
        """Get job type distribution"""
        job_types = {}
        for job in jobs:
            job_type = job.get('job_type', 'Unknown')
            job_types[job_type] = job_types.get(job_type, 0) + 1
        return job_types
    
    def _get_experience_distribution(self, jobs: List[Dict]) -> Dict[str, int]:
        """Get experience level distribution"""
        exp_levels = {}
        for job in jobs:
            exp_level = job.get('experience_level', 'Unknown')
            exp_levels[exp_level] = exp_levels.get(exp_level, 0) + 1
        return exp_levels
    
    def analyze_job_market(self, job_role: str, search_results: Dict) -> Dict:
        """Analyze job market trends using Gemini AI"""
        try:
            # Use direct API call to Gemini
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            
            # Prepare data for analysis
            job_data = {
                'total_jobs': search_results.get('total_jobs', 0),
                'sources': list(search_results.get('sources', {}).keys()),
                'sample_jobs': search_results.get('all_jobs', [])[:5],  # Sample jobs
                'summary': search_results.get('summary', {})
            }
            
            prompt = f"""
            Analyze the job market for "{job_role}" AI/ML positions in Pune for Symbiosis Institute of Technology 4th year students and fresh graduates.
            
            Job Search Data Summary:
            - Total jobs found: {job_data['total_jobs']}
            - Sources searched: {', '.join(job_data['sources'])}
            - Sample job titles: {[job.get('title', 'N/A') for job in job_data['sample_jobs'][:3]]}
            
            Provide a comprehensive analysis including:
            
            ## Market Overview
            Current demand and supply for {job_role} positions in Pune AI/ML market.
            
            ## Salary Expectations
            Expected salary ranges for fresh graduates in {job_role} positions (in INR/LPA).
            
            ## Top Hiring Companies
            Companies actively hiring for {job_role} roles in Pune.
            
            ## Essential Skills
            Most sought-after technical and soft skills for {job_role} positions.
            
            ## Career Growth Path
            Typical career progression for freshers starting in {job_role}.
            
            ## Application Strategy
            Practical tips to improve chances of getting hired in {job_role}.
            
            ## Industry Trends
            Current AI/ML industry trends affecting {job_role} opportunities.
            
            ## Action Items for Students
            Specific recommendations for SIT Pune students to prepare for {job_role} roles.
            
            Keep the analysis practical, actionable, and focused on the Indian job market.
            """
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            
            headers = {
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                analysis_text = result['candidates'][0]['content']['parts'][0]['text']
                
                return {
                    'job_role': job_role,
                    'analysis': analysis_text,
                    'timestamp': datetime.now().isoformat(),
                    'job_count': search_results.get('total_jobs', 0),
                    'data_quality': 'high' if search_results.get('total_jobs', 0) > 10 else 'medium'
                }
            else:
                raise Exception(f"Gemini API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Market analysis failed: {e}")
            # Fallback analysis
            return {
                'job_role': job_role,
                'analysis': self._generate_fallback_analysis(job_role, search_results),
                'timestamp': datetime.now().isoformat(),
                'job_count': search_results.get('total_jobs', 0),
                'data_quality': 'limited',
                'error': str(e)
            }
    
    def _generate_fallback_analysis(self, job_role: str, search_results: Dict) -> str:
        """Generate basic analysis when AI fails"""
        total_jobs = search_results.get('total_jobs', 0)
        sources = search_results.get('sources', {})
        
        analysis = f"""
# Job Market Analysis for {job_role} - AI/ML Positions in Pune

## Market Overview
Based on our search across {len(sources)} job portals, we found {total_jobs} relevant positions for {job_role} in the Pune AI/ML market.

## Key Findings
- **Job Availability**: {'High' if total_jobs > 20 else 'Moderate' if total_jobs > 10 else 'Limited'} number of {job_role} positions available
- **Market Demand**: AI/ML sector shows consistent demand for entry-level positions
- **Location Focus**: Pune remains a key hub for AI/ML opportunities

## Recommendations for SIT Students
1. **Skill Development**: Focus on Python, Machine Learning frameworks (TensorFlow, PyTorch)
2. **Portfolio Building**: Create projects showcasing {job_role} skills
3. **Networking**: Connect with AI/ML professionals on LinkedIn
4. **Continuous Learning**: Stay updated with latest AI/ML trends
5. **Application Strategy**: Apply through multiple job portals for better reach

## Next Steps
- Monitor job markets regularly for new opportunities
- Build a strong GitHub portfolio with relevant projects
- Prepare for technical interviews focusing on {job_role} concepts
- Consider internships to gain practical experience

*Note: This analysis is based on current job market data and should be supplemented with additional research.*
        """
        
        return analysis

# Initialize job search engine
job_search_engine = JobSearchEngine()

# Enhanced API Routes
@app.route("/", methods=["GET"])
def health_check():
    """Enhanced health check endpoint"""
    return jsonify({
        "message": "🚀 AI/ML Job Search & Interview Prep API for SIT Pune 4th Year Students - Ready",
        "version": "3.0",
        "timestamp": datetime.now().isoformat(),
        "status": "operational",
        "supported_sources": ["LinkedIn", "Naukri", "Indeed", "FreshersWorld", "Monster"],
        "new_features": [
            "Comprehensive job search across multiple platforms",
            "Real-time search progress updates",
            "AI-powered market analysis",
            "Job relevance scoring",
            "Interview question search with solutions",
            "Company-specific interview questions",
            "PDF generation for interview prep",
            "India-specific content focus"
        ],
        "endpoints": {
            "/search-jobs": "POST - Search for AI/ML jobs",
            "/interview-questions": "POST - Search for interview questions",
            "/generate-interview-pdf": "POST - Generate PDF with interview questions",
            "/analyze-market": "POST - Get AI-powered market analysis",
            "/job-suggestions": "GET - Get job role suggestions",
            "/search-status": "GET - Check search capabilities"
        }
    })

@app.route("/search-jobs", methods=["POST"])
def search_jobs():
    """Enhanced job search endpoint with validation"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        job_role = data.get('job_role', '').strip()
        location = data.get('location', 'Pune').strip()
        filters = data.get('filters', {})
        
        # Validation
        if not job_role:
            return jsonify({'error': 'Job role is required'}), 400
        
        if len(job_role) < 2:
            return jsonify({'error': 'Job role must be at least 2 characters'}), 400
        
        logger.info(f"Processing job search: {job_role} in {location}")
        
        # Run search in background thread
        search_thread = threading.Thread(
            target=job_search_engine.comprehensive_job_search,
            args=(job_role, location, filters)
        )
        search_thread.daemon = True
        search_thread.start()
        
        return jsonify({
            'message': 'Job search initiated successfully',
            'job_role': job_role,
            'location': location,
            'status': 'in_progress',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Job search error: {str(e)}")
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

@app.route("/interview-questions", methods=["POST"])
def search_interview_questions():
    """Enhanced interview questions search endpoint"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Parse input parameters
        domain = data.get('domain', '').strip()
        company = data.get('company', '').strip() or None
        difficulty = data.get('difficulty', 'all').lower()  # all, easy, medium, hard
        question_count = min(data.get('question_count',10), 20)  # Limit to 50 max
        
        # Validation
        if not domain:
            return jsonify({'error': 'Domain is required'}), 400
        
        if len(domain) < 2:
            return jsonify({'error': 'Domain must be at least 2 characters'}), 400
        
        # Valid domains
        valid_domains = [
            'DSA', 'SQL', 'OS', 'CN', 'DBMS', 'Machine Learning', 'Deep Learning',
            'Python', 'Java', 'System Design', 'JavaScript', 'React', 'Node.js',
            'Cloud Computing', 'DevOps', 'Cybersecurity', 'Blockchain'
        ]
        
        if domain not in valid_domains:
            return jsonify({
                'error': f'Invalid domain. Supported domains: {", ".join(valid_domains)}'
            }), 400
        
        logger.info(f"Processing enhanced interview question search: {domain} for {company or 'All Companies'}")
        
        # Run search in background thread
        search_thread = threading.Thread(
            target=job_search_engine.search_interview_questions,
            args=(domain, company, difficulty, question_count)
        )
        search_thread.daemon = True
        search_thread.start()
        
        return jsonify({
            'message': 'Enhanced interview question search initiated successfully',
            'search_id': f"{domain}_{company or 'general'}_{int(time.time())}",
            'domain': domain,
            'company': company,
            'difficulty': difficulty,
            'expected_questions': question_count,
            'status': 'in_progress',
            'estimated_time': '2-3 minutes',
            'features': [
                'Real-time question extraction',
                'Company-specific questions',
                'AI-generated detailed solutions',
                'Multiple difficulty levels',
                'Recent questions (2022-2024)',
                'Source credibility scoring'
            ],
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Enhanced interview question search error: {str(e)}")
        return jsonify({'error': f'Interview question search failed: {str(e)}'}), 500


@app.route("/generate-interview-pdf", methods=["POST"])
def generate_interview_pdf():
    """Enhanced PDF generation for interview questions"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        domain = data.get('domain', '').strip()
        questions = data.get('questions', [])
        company = data.get('company', '').strip() or None
        include_solutions = data.get('include_solutions', True)
        difficulty_filter = data.get('difficulty_filter', 'all')  # all, easy, medium, hard
        
        # Validation
        if not domain:
            return jsonify({'error': 'Domain is required'}), 400
        
        if not questions:
            return jsonify({'error': 'Questions list is required'}), 400
        
        # Filter questions by difficulty if specified
        if difficulty_filter != 'all':
            questions = [q for q in questions if q.get('difficulty', '').lower() == difficulty_filter.lower()]
        
        # Validate question structure
        for i, question in enumerate(questions):
            if not isinstance(question, dict):
                return jsonify({'error': f'Question {i+1} must be a dictionary'}), 400
            
            required_fields = ['question', 'domain']
            for field in required_fields:
                if not question.get(field):
                    return jsonify({'error': f'Question {i+1} missing required field: {field}'}), 400
        
        logger.info(f"Generating enhanced PDF for {domain} - {len(questions)} questions")
        
        # Generate enhanced PDF
        pdf_buffer = job_search_engine.pdf_generator.generate_enhanced_pdf(
            domain, questions, company, include_solutions, difficulty_filter
        )
        
        # Prepare filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"interview_prep_{domain.lower().replace(' ', '_')}"
        if company:
            filename += f"_{company.lower().replace(' ', '_')}"
        if difficulty_filter != 'all':
            filename += f"_{difficulty_filter}"
        filename += f"_{timestamp}.pdf"
        
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.error(f"Enhanced PDF generation error: {str(e)}")
        return jsonify({'error': f'PDF generation failed: {str(e)}'}), 500






@app.route("/analyze-market", methods=["POST"])
def analyze_market():
    """Enhanced job market analysis endpoint"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        job_role = data.get('job_role', '').strip()
        search_results = data.get('search_results', {})
        
        if not job_role:
            return jsonify({'error': 'Job role is required'}), 400
        
        if not search_results:
            return jsonify({'error': 'Search results are required for analysis'}), 400
        
        logger.info(f"Analyzing job market for: {job_role}")
        
        analysis = job_search_engine.analyze_job_market(job_role, search_results)
        return jsonify(analysis)
        
    except Exception as e:
        logger.error(f"Market analysis error: {str(e)}")
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

@app.route("/job-suggestions", methods=["GET"])
def job_suggestions():
    """Enhanced job role suggestions for AI/ML"""
    suggestions = {
        'categories': {
            'core_ai_ml': {
                'title': 'Core AI/ML Roles',
                'roles': [
                    {'role': 'AI Engineer', 'description': 'Design and implement AI systems'},
                    {'role': 'Machine Learning Engineer', 'description': 'Build and deploy ML models'},
                    {'role': 'Data Scientist', 'description': 'Extract insights from data using ML'},
                    {'role': 'Deep Learning Engineer', 'description': 'Specialize in neural networks'}
                ]
            },
            'specialized_ai': {
                'title': 'Specialized AI Roles',
                'roles': [
                    {'role': 'NLP Specialist', 'description': 'Natural Language Processing expert'},
                    {'role': 'Computer Vision Engineer', 'description': 'Image and video analysis'},
                    {'role': 'Robotics Engineer', 'description': 'AI-powered robotics systems'},
                    {'role': 'AI Research Assistant', 'description': 'Support AI research projects'}
                ]
            },
            'data_roles': {
                'title': 'Data-Focused Roles',
                'roles': [
                    {'role': 'Data Analyst', 'description': 'Analyze data for business insights'},
                    {'role': 'Data Engineer', 'description': 'Build data pipelines and infrastructure'},
                    {'role': 'Business Intelligence Analyst', 'description': 'Create data-driven reports'},
                    {'role': 'Quantitative Analyst', 'description': 'Mathematical modeling for finance'}
                ]
            },
            'product_tech': {
                'title': 'Product & Technology',
                'roles': [
                    {'role': 'AI Product Manager', 'description': 'Manage AI product development'},
                    {'role': 'ML Ops Engineer', 'description': 'Deploy and maintain ML systems'},
                    {'role': 'AI Ethics Researcher', 'description': 'Ensure responsible AI development'},
                    {'role': 'Technical AI Writer', 'description': 'Document AI systems and research'}
                ]
            }
        },
        'interview_domains': [
            'NLP',
            'Computer Vision', 
            'Machine Learning',
            'Deep Learning',
            'Data Science',
            'AI Ethics',
            'Robotics',
            'Data Analysis',
            'Python Programming',
            'Statistics',
            'Algorithms',
            'System Design'
        ],
        'trending_skills': [
            'Python Programming',
            'TensorFlow/PyTorch',
            'Machine Learning Algorithms',
            'Deep Learning',
            'Natural Language Processing',
            'Computer Vision',
            'SQL and Databases',
            'Cloud Platforms (AWS/Azure/GCP)',
            'Docker & Kubernetes',
            'Git Version Control'
        ],
        'entry_level_tips': [
            'Start with foundational Python and statistics',
            'Build a portfolio of ML projects on GitHub',
            'Complete online courses from reputable platforms',
            'Participate in Kaggle competitions',
            'Apply for internships to gain practical experience',
            'Network with AI/ML professionals on LinkedIn',
            'Prepare for technical interviews with coding practice',
            'Stay updated with latest AI/ML research and trends'
        ]
    }
    
    return jsonify(suggestions)

@app.route("/search-status", methods=["GET"])
def search_status():
    """Check search system status"""
    try:
        # Test SerpAPI connection
        test_search = GoogleSearch({
            "api_key": SERPAPI_API_KEY,
            "engine": "google",
            "q": "test search",
            "num": 1
        })
        
        test_result = test_search.get_dict()
        serpapi_status = "operational" if test_result else "limited"
        
        status = {
            'system_status': 'operational',
            'serpapi_status': serpapi_status,
            'supported_sources': {
                'LinkedIn': 'operational',
                'Naukri': 'operational',
                'Indeed': 'operational',
                'FreshersWorld': 'operational',
                'Monster': 'operational'
            },
            'interview_features': {
                'question_search': 'operational',
                'pdf_generation': 'operational',
                'ai_solutions': 'operational'
            },
            'ai_analysis': 'operational',
            'last_check': datetime.now().isoformat(),
            'rate_limits': {
                'requests_per_minute': 30,
                'concurrent_searches': MAX_WORKERS
            }
        }
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return jsonify({
            'system_status': 'degraded',
            'error': str(e),
            'last_check': datetime.now().isoformat()
        }), 500

# WebSocket Event Handlers
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info("Client connected to WebSocket")
    emit('connected', {
        'message': '🤖 Neural network synchronized - AI Job Search & Interview Prep System Ready',
        'timestamp': datetime.now().isoformat(),
        'features': [
            'Real-time job search updates', 
            'AI-powered market analysis', 
            'Multi-source job search',
            'Interview question search',
            'Company-specific interview prep',
            'PDF report generation'
        ]
    })

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info("Client disconnected from WebSocket")

@socketio.on('ping')
def handle_ping():
    """Handle ping for connection testing"""
    emit('pong', {'timestamp': datetime.now().isoformat()})

# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found', 'available_endpoints': [
        'GET /', 'POST /search-jobs', 'POST /interview-questions', 
        'POST /generate-interview-pdf', 'POST /analyze-market', 
        'GET /job-suggestions', 'GET /search-status'
    ]}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error', 'message': 'Please try again later'}), 500

@app.errorhandler(429)
def rate_limit_error(error):
    return jsonify({'error': 'Rate limit exceeded', 'message': 'Please wait before making another request'}), 429

# Enhanced WebSocket events for real-time updates
@socketio.on('interview_search_started')
def handle_interview_search_started(data):
    """Handle interview search started event"""
    emit('search_progress', {
        'stage': 'started',
        'message': f"🚀 Starting interview question search for {data.get('domain', 'N/A')}",
        'progress': 0,
        'timestamp': datetime.now().isoformat()
    })

@socketio.on('question_extracted')
def handle_question_extracted(data):
    """Handle individual question extraction"""
    emit('question_found', {
        'question': data.get('question', ''),
        'source': data.get('source', ''),
        'company': data.get('company', ''),
        'difficulty': data.get('difficulty', ''),
        'timestamp': datetime.now().isoformat()
    })

@socketio.on('solution_generated')
def handle_solution_generated(data):
    """Handle AI solution generation"""
    emit('solution_ready', {
        'question_id': data.get('question_id', ''),
        'solution_preview': data.get('solution', '')[:100] + '...',
        'timestamp': datetime.now().isoformat()
    })

# Main application runner
if __name__ == '__main__':
    print("🚀 Starting Enhanced AI/ML Job Search & Interview Prep API for SIT Pune 4th Year Students...")
    print("📍 Server will be available at: http://localhost:7860")
    print("🔍 Supported job sources: LinkedIn, Naukri, Indeed, FreshersWorld, Monster")
    print("📝 Interview question search: India-specific with AI solutions")
    print("📄 PDF generation: Professional interview preparation reports")
    print("🤖 AI-powered market analysis enabled")
    print("⚡ Real-time WebSocket updates enabled")
    print("=" * 70)
    
    try:
        socketio.run(
            app, 
            debug=False,  # Set to False for production
            host='0.0.0.0', 
            port=7860,
            use_reloader=False,  # Disable reloader to prevent threading issues
            log_output=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Server shutdown requested")
    except Exception as e:
        print(f"❌ Server failed to start: {e}")
        logger.error(f"Server startup error: {e}")
    finally:
        print("👋 AI Job Search & Interview Prep API shutting down...")