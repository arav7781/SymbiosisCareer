"use client"
import { useEffect, useRef, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import io from "socket.io-client"
import {
  Search,
  MapPin,
  Briefcase,
  Building,
  Clock,
  ExternalLink,
  Star,
  Filter,
  Bookmark,
  DollarSign,
  AlertCircle,
  Loader2,
  Shield,
  Wifi,
  WifiOff,
  Activity,
  CheckCircle,
  GraduationCap,
  FileText,
  ChevronDown,
  ChevronUp,
  Menu,
  X,
} from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "https://aravsaxena884-job-search.hf.space"
const socket = io(API_BASE, {
  transports: ["polling"],
  path: "/socket.io",
  reconnection: true,
  reconnectionAttempts: 10,
  reconnectionDelay: 1000,
})

interface Thought {
  agent: string
  message: string
  timestamp: Date
}

interface Job {
  title: string
  company: string
  location: string
  description: string
  url: string
  salary?: string
  job_type?: string
  experience_level?: string
  source: string
  relevance_score?: number
}

interface InterviewQuestion {
  question: string
  solution: string
  domain: string
  company?: string
  year?: number
  source_url?: string
  source_title?: string
  difficulty?: string
  source_type?: string
  credibility_score?: number
  question_type?: string
  relevance_score?: number
}

interface SearchResults {
  total_jobs: number
  all_jobs: Job[]
  market_analysis?: {
    job_role: string
    analysis: string
    job_count: number
    timestamp: string
  }
}

interface InterviewResults {
  domain: string
  company?: string
  difficulty: string
  questions: InterviewQuestion[]
  total_questions: number
  search_metadata?: {
    sources_searched: number
    search_queries_used: number
    credibility_filtered: boolean
    ai_enhanced: boolean
    recent_questions_only: boolean
  }
  timestamp: string
}

export default function SITJobSearchApp() {
  const [jobRole, setJobRole] = useState("")
  const [location, setLocation] = useState("Pune")
  const [searchResults, setSearchResults] = useState<SearchResults | null>(null)
  const [interviewResults, setInterviewResults] = useState<InterviewResults | null>(null)
  const [loading, setLoading] = useState(false)
  const [interviewLoading, setInterviewLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [showFilters, setShowFilters] = useState(false)
  const [filters, setFilters] = useState({
    experience_level: "entry",
    job_type: "all",
    salary_range: "all",
  })
  const [thoughts, setThoughts] = useState<Thought[]>([])
  const [connectionStatus, setConnectionStatus] = useState("Establishing quantum link...")
  const [status, setStatus] = useState("System initialized - Ready for search")
  const [error, setError] = useState("")
  const [savedJobs, setSavedJobs] = useState<Job[]>([])
  const [showCandidatesAnimation, setShowCandidatesAnimation] = useState(false)
  const [activeTab, setActiveTab] = useState<"interview" | "jobs">("interview")
  const [interviewDomain, setInterviewDomain] = useState("")
  const [interviewCompany, setInterviewCompany] = useState("")
  const [difficultyFilter, setDifficultyFilter] = useState("all")
  const [expandedQuestions, setExpandedQuestions] = useState<Set<number>>(new Set())
  const thoughtsEndRef = useRef<HTMLDivElement>(null)
  const [showMobileLogs, setShowMobileLogs] = useState(false)

  const popularRoles = [
    "AI Engineer",
    "Machine Learning Engineer",
    "Data Scientist",
    "NLP Specialist",
    "Computer Vision Engineer",
    "Deep Learning Engineer",
    "AI Research Assistant",
    "ML Ops Engineer",
    "AI Product Manager",
    "Data Analyst",
    "Robotics Engineer",
    "AI Ethicist",
  ]

  const indianCities = [
    "Pune",
    "Mumbai",
    "Bangalore",
    "Hyderabad",
    "Delhi",
    "Chennai",
    "Gurgaon",
    "Noida",
    "Ahmedabad",
    "Kolhapur",
    "Nashik",
    "Nagpur",
  ]

  const popularDomains = [
    "DSA",
    "SQL",
    "OS",
    "CN",
    "DBMS",
    "Machine Learning",
    "Deep Learning",
    "Python",
    "Java",
    "System Design",
    "JavaScript",
    "React",
    "Node.js",
    "Cloud Computing",
    "DevOps",
    "Cybersecurity",
    "Blockchain",
  ]

  useEffect(() => {
    // Fetch suggestions once on mount
    ;(async () => {
      try {
        const response = await fetch(`${API_BASE}/job-suggestions`)
        if (response.ok) {
          const data: unknown = await response.json()
          const list: string[] = isStringArray(data) ? data : hasSuggestions(data) ? data.suggestions : []
          setSuggestions(list)
        }
      } catch (e) {
        console.error("Error fetching suggestions:", e)
      }
    })()

    socket.on("connect", () => {
      setConnectionStatus("Quantum link established")
    })

    socket.on("disconnect", () => {
      setConnectionStatus("Connection lost")
      setError("Lost connection to server. Please try again.")
    })

    socket.io.on("error", (err: unknown) => {
      console.warn("Socket manager error", err)
      setConnectionStatus("Connection issue")
    })

    socket.on("connect_error", (err: unknown) => {
      console.warn("Socket connect_error", err)
      setConnectionStatus("Connection error - retrying")
    })

    socket.on("reconnect_attempt", () => {
      setConnectionStatus("Reconnecting...")
    })

    socket.on("reconnect_failed", () => {
      setConnectionStatus("Reconnect failed")
    })

    socket.on("connected", (data: { message: string }) => {
      console.log("Backend confirmation:", data.message)
      setStatus(data.message)
    })

    socket.on("thought", (data: Thought) => {
      setThoughts((prev) => [...prev, { ...data, timestamp: new Date() }])
    })

    socket.on("search_started", (data: { job_role: string; location: string }) => {
      setStatus(`Search initiated for ${data.job_role} in ${data.location}`)
    })

    socket.on("source_completed", (data: { source: string; job_count: number }) => {
      setStatus(`${data.source} completed - ${data.job_count} jobs found`)
    })

    socket.on("search_completed", (data: SearchResults) => {
      setSearchResults(data)
      setLoading(false)
      setStatus(`Search completed - ${data.total_jobs} jobs found`)
      setShowCandidatesAnimation(true)
      setTimeout(() => setShowCandidatesAnimation(false), 2000)
    })

    socket.on("search_failed", (data: { error?: string }) => {
      setError(data.error || "Search failed. Please try again.")
      setLoading(false)
      setStatus("Search failed")
    })

    socket.on("interview_search_started", (data: { message: string; domain: string; company?: string }) => {
      setStatus(data.message)
    })

    socket.on(
      "question_extracted",
      (data: {
        question: string
        source: string
        company?: string
        difficulty?: string
        timestamp: string
      }) => {
        setStatus(`Found question: ${data.question.slice(0, 50)}... from ${data.source}`)
      },
    )

    socket.on("solution_generated", (data: { question_id: string; solution_preview: string; timestamp: string }) => {
      setStatus(`Solution generated for question ${data.question_id}`)
    })

    socket.on("interview_search_completed", (data: InterviewResults) => {
      console.log("Interview Search Completed:", data) // Debug log
      setInterviewResults(data)
      setInterviewLoading(false)
      setStatus(`Interview question search completed - ${data.total_questions} questions found`)
    })

    socket.on("interview_search_failed", (data: { error: string; domain: string; company?: string }) => {
      setError(data.error || "Interview question search failed. Please try again.")
      setInterviewLoading(false)
      setStatus("Interview question search failed")
    })

    return () => {
      socket.off("connect")
      socket.off("disconnect")
      socket.off("connected")
      socket.off("thought")
      socket.off("search_started")
      socket.off("source_completed")
      socket.off("search_completed")
      socket.off("search_failed")
      socket.off("interview_search_started")
      socket.off("question_extracted")
      socket.off("solution_generated")
      socket.off("interview_search_completed")
      socket.off("interview_search_failed")
      socket.io.off("error")
      socket.off("connect_error")
      socket.off("reconnect_attempt")
      socket.off("reconnect_failed")
    }
  }, [])

  const scrollToBottom = () => {
    setTimeout(() => {
      if (thoughtsEndRef.current) {
        const container = thoughtsEndRef.current.closest(".overflow-y-auto")
        if (container) {
          ;(container as HTMLElement).scrollTo({
            top: (container as HTMLElement).scrollHeight,
            behavior: "smooth",
          })
        }
      }
    }, 100)
  }

  useEffect(() => {
    if (thoughts.length > 0) {
      scrollToBottom()
    }
  }, [thoughts])

  const isStringArray = (x: unknown): x is string[] => Array.isArray(x) && x.every((i) => typeof i === "string")

  const hasSuggestions = (
    x: unknown,
  ): x is {
    suggestions: string[]
  } => {
    if (typeof x !== "object" || x === null || !("suggestions" in x)) return false
    const s = (x as { suggestions: unknown }).suggestions
    return Array.isArray(s) && s.every((i) => typeof i === "string")
  }

  const searchJobs = async () => {
    if (!jobRole.trim()) {
      setError("Please enter a job role")
      return
    }

    setLoading(true)
    setThoughts([])
    setSearchResults(null)
    setError("")
    setStatus("Initiating neural job search...")

    try {
      const response = await fetch(`${API_BASE}/search-jobs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          job_role: jobRole,
          location: location,
          filters: filters,
        }),
      })

      if (!response.ok) {
        throw new Error("Search initiation failed")
      }
    } catch (error) {
      console.error("Search error:", error)
      setError("Search failed. Please check your connection and try again.")
      setLoading(false)
      setStatus("Search failed")
    }
  }

  const searchInterviewQuestions = async () => {
    if (!interviewDomain.trim()) {
      setError("Please enter a domain for interview questions")
      return
    }

    setInterviewLoading(true)
    setThoughts([])
    setInterviewResults(null)
    setError("")
    setStatus("Initiating interview question search...")

    try {
      const response = await fetch(`${API_BASE}/interview-questions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          domain: interviewDomain,
          company: interviewCompany.trim() || undefined,
          difficulty: difficultyFilter,
          question_count: 20,
        }),
      })

      if (!response.ok) {
        throw new Error("Interview question search initiation failed")
      }

      const data = await response.json()
      console.log("API Response:", data) // Debug log
      setStatus(data.message || "Interview question search initiated")
    } catch (error) {
      console.error("Interview question search error:", error)
      setError("Interview question search failed. Please check your connection and try again.")
      setInterviewLoading(false)
      setStatus("Interview question search failed")
    }
  }

  const downloadPDF = async () => {
    if (!interviewResults) return

    try {
      const response = await fetch(`${API_BASE}/generate-interview-pdf`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          domain: interviewResults.domain,
          questions: interviewResults.questions,
          company: interviewResults.company,
          include_solutions: true,
          difficulty_filter: difficultyFilter,
        }),
      })

      if (!response.ok) {
        throw new Error("PDF generation failed")
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `interview_questions_${interviewResults.domain}_${Date.now()}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error("PDF download error:", error)
      setError("Failed to generate PDF. Please try again.")
    }
  }

  const toggleSavedJob = (job: Job) => {
    setSavedJobs((prev) => {
      const isSaved = prev.some((savedJob) => savedJob.url === job.url)
      if (isSaved) {
        return prev.filter((savedJob) => savedJob.url !== job.url)
      }
      return [...prev, job]
    })
  }

  const toggleQuestionExpansion = (index: number) => {
    setExpandedQuestions((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(index)) {
        newSet.delete(index)
      } else {
        newSet.add(index)
      }
      return newSet
    })
  }

  const formatTimestamp = (date: Date) => {
    return date.toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
  }

  const getAgentColor = (agent: string) => {
    const colors = [
      "text-blue-600 border-blue-600",
      "text-indigo-600 border-indigo-600",
      "text-cyan-600 border-cyan-600",
      "text-teal-600 border-teal-600",
      "text-slate-600 border-slate-600",
    ]
    const hash = agent.split("").reduce((a, b) => a + b.charCodeAt(0), 0)
    return colors[hash % colors.length]
  }

  const getScoreColor = (score: number) => {
    if (score >= 8) return "from-emerald-500 to-green-600"
    if (score >= 6) return "from-blue-500 to-indigo-500"
    return "from-slate-500 to-gray-600"
  }

  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty?.toLowerCase()) {
      case "hard":
        return "bg-red-100 text-red-700"
      case "medium":
        return "bg-yellow-100 text-yellow-700"
      case "easy":
        return "bg-green-100 text-green-700"
      default:
        return "bg-gray-100 text-gray-700"
    }
  }

  const JobCard = ({ job, index }: { job: Job; index: number }) => {
    const isSaved = savedJobs.some((savedJob) => savedJob.url === job.url)
    return (
      <motion.div
        className="bg-white/95 backdrop-blur-xl rounded-xl sm:rounded-2xl border-2 border-blue-200 overflow-hidden shadow-xl hover:shadow-2xl transition-all duration-300"
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: index * 0.1, duration: 0.6 }}
        whileHover={{ scale: 1.01, y: -2 }}
      >
        <div className="p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between mb-4 gap-3 sm:gap-0">
            <div className="flex items-start">
              <motion.div
                className="w-10 h-10 sm:w-12 sm:h-12 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-full flex items-center justify-center text-white font-bold mr-3 sm:mr-4 text-base sm:text-lg shadow-lg flex-shrink-0"
                whileHover={{ rotate: 360 }}
                transition={{ duration: 0.5 }}
              >
                <Briefcase className="w-5 h-5 sm:w-6 sm:h-6" />
              </motion.div>
              <div className="flex-1 min-w-0">
                <h3 className="font-bold text-gray-800 text-lg sm:text-xl mb-1 break-words">{job.title}</h3>
                <div className="flex flex-col sm:flex-row sm:items-center text-gray-600 mb-2 gap-1 sm:gap-0">
                  <div className="flex items-center">
                    <Building className="w-4 h-4 mr-2 flex-shrink-0" />
                    <span className="font-medium break-words">{job.company}</span>
                  </div>
                  <span className="hidden sm:block ml-4 flex items-center">
                    <MapPin className="w-4 h-4 mr-1 flex-shrink-0" />
                    {job.location}
                  </span>
                  <div className="flex items-center sm:hidden">
                    <MapPin className="w-4 h-4 mr-1 flex-shrink-0" />
                    <span className="break-words">{job.location}</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex items-center justify-between sm:justify-end space-x-3">
              {job.relevance_score && (
                <motion.div
                  className={`px-3 sm:px-4 py-1.5 sm:py-2 rounded-full bg-gradient-to-r ${getScoreColor(
                    job.relevance_score / 10,
                  )} text-white font-bold text-xs sm:text-sm shadow-lg border-2 border-white`}
                  whileHover={{ scale: 1.05 }}
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: index * 0.1 + 0.3, type: "spring", stiffness: 200 }}
                >
                  {Math.round(job.relevance_score / 10)}/10
                </motion.div>
              )}
              <button
                onClick={() => toggleSavedJob(job)}
                className={`p-2 rounded-full ${
                  isSaved ? "text-blue-600 bg-blue-100" : "text-gray-400 bg-gray-100"
                } hover:text-blue-700 transition-colors`}
                aria-label={isSaved ? "Remove from saved jobs" : "Save job"}
              >
                <Bookmark className="w-4 h-4 sm:w-5 sm:h-5" />
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center text-xs sm:text-sm text-gray-500 mb-4 gap-2">
            <div className="flex items-center">
              <Clock className="w-3 h-3 sm:w-4 sm:h-4 mr-1" />
              <span>{job.experience_level || "Entry Level"}</span>
            </div>
            <span className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-2 sm:px-3 py-1 rounded-full text-xs font-bold">
              {job.source}
            </span>
          </div>

          <p className="text-gray-600 mb-4 line-clamp-3 leading-relaxed text-sm sm:text-base break-words">
            {job.description}
          </p>

          {job.salary && job.salary !== "Not Disclosed" && (
            <div className="flex items-center text-emerald-600 mb-4 bg-emerald-50 px-3 py-2 rounded-lg">
              <DollarSign className="w-4 h-4 mr-1 flex-shrink-0" />
              <span className="font-semibold text-sm sm:text-base break-words">{job.salary}</span>
            </div>
          )}

          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 sm:gap-0">
            <div className="flex items-center space-x-4">
              <div className="flex items-center text-xs sm:text-sm text-blue-600">
                <Star className="w-3 h-3 sm:w-4 sm:h-4 mr-1" />
                <span>SIT Match</span>
              </div>
            </div>
            <motion.a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full sm:w-auto inline-flex items-center justify-center px-4 sm:px-6 py-2.5 sm:py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-lg sm:rounded-xl hover:from-blue-700 hover:to-indigo-700 transition-all duration-300 text-xs sm:text-sm font-bold shadow-lg"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              aria-label={`Apply for ${job.title} at ${job.company}`}
            >
              <ExternalLink className="w-3 h-3 sm:w-4 sm:h-4 mr-1 sm:mr-2" />
              APPLY NOW
            </motion.a>
          </div>
        </div>
      </motion.div>
    )
  }

  const InterviewQuestionCard = ({ question, index }: { question: InterviewQuestion; index: number }) => {
    const isExpanded = expandedQuestions.has(index)
    return (
      <motion.div
        className="bg-white/95 backdrop-blur-xl rounded-xl sm:rounded-2xl border-2 border-blue-200 overflow-hidden shadow-xl hover:shadow-2xl transition-all duration-300"
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: index * 0.1, duration: 0.6 }}
        whileHover={{ scale: 1.01, y: -2 }}
      >
        <div className="p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between mb-4 gap-3 sm:gap-0">
            <div className="flex-1 min-w-0">
              <h3 className="font-bold text-gray-800 text-lg sm:text-xl mb-1">Question {index + 1}</h3>
              <p className="text-gray-600 mb-2 text-base sm:text-lg font-medium break-words">{question.question}</p>
              <div className="flex flex-wrap items-center text-gray-600 mb-2 gap-2 sm:gap-4">
                {question.company && (
                  <span className="flex items-center text-sm">
                    <Building className="w-3 h-3 sm:w-4 sm:h-4 mr-1 sm:mr-2 flex-shrink-0" />
                    <span className="break-words">{question.company}</span>
                    {question.year && <span className="ml-1 sm:ml-2">({question.year})</span>}
                  </span>
                )}
                {question.difficulty && (
                  <span
                    className={`px-2 sm:px-3 py-1 rounded-full text-xs sm:text-sm font-semibold ${getDifficultyColor(question.difficulty)}`}
                  >
                    {question.difficulty}
                  </span>
                )}
                {question.question_type && (
                  <span className="px-2 sm:px-3 py-1 rounded-full text-xs sm:text-sm font-semibold bg-blue-100 text-blue-700">
                    {question.question_type}
                  </span>
                )}
              </div>
              {question.source_url && (
                <a
                  href={question.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 text-xs sm:text-sm hover:underline flex items-center break-all"
                >
                  <ExternalLink className="w-3 h-3 sm:w-4 sm:h-4 mr-1 flex-shrink-0" />
                  Source: {question.source_title || question.source_url}
                </a>
              )}
              {question.credibility_score && (
                <div className="text-xs sm:text-sm text-gray-500 mt-2">
                  Credibility Score: {question.credibility_score}/10
                </div>
              )}
            </div>
            <button
              onClick={() => toggleQuestionExpansion(index)}
              className="self-start sm:self-auto p-2 rounded-full bg-blue-100 text-blue-600 hover:bg-blue-200 transition-colors flex-shrink-0"
              aria-label={isExpanded ? "Collapse solution" : "Expand solution"}
            >
              {isExpanded ? (
                <ChevronUp className="w-4 h-4 sm:w-5 sm:h-5" />
              ) : (
                <ChevronDown className="w-4 h-4 sm:w-5 sm:h-5" />
              )}
            </button>
          </div>
          <AnimatePresence>
            {isExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="text-gray-600"
              >
                <h4 className="font-semibold text-blue-600 mb-2 text-sm sm:text-base">Solution:</h4>
                <div
                  className="leading-relaxed whitespace-pre-wrap markdown-body text-sm sm:text-base break-words"
                  dangerouslySetInnerHTML={{ __html: question.solution || "Solution not available." }}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 relative overflow-hidden">
      <style jsx global>{`
        .markdown-body pre {
          background: #f6f8fa;
          padding: 16px;
          border-radius: 6px;
          overflow-x: auto;
        }
        .markdown-body code {
          background: #f6f8fa;
          padding: 2px 4px;
          border-radius: 4px;
        }
        .markdown-body h2 {
          font-size: 1.5rem;
          font-weight: bold;
          margin-top: 1rem;
          margin-bottom: 0.5rem;
        }
        .markdown-body ul {
          list-style: disc;
          padding-left: 2rem;
          margin-bottom: 1rem;
        }
        .markdown-body p {
          margin-bottom: 1rem;
        }
        
        /* Enhanced scrollbar styles for better mobile experience */
        .scrollbar-thin {
          scrollbar-width: thin;
        }
        .scrollbar-thumb-blue-500::-webkit-scrollbar {
          width: 6px;
        }
        .scrollbar-thumb-blue-500::-webkit-scrollbar-track {
          background: #f1f5f9;
          border-radius: 3px;
        }
        .scrollbar-thumb-blue-500::-webkit-scrollbar-thumb {
          background: #3b82f6;
          border-radius: 3px;
        }
        .scrollbar-thumb-blue-500::-webkit-scrollbar-thumb:hover {
          background: #2563eb;
        }
      `}</style>

      <div className="absolute inset-0 opacity-20">
        <div className="absolute top-0 left-0 w-72 h-72 bg-blue-300 rounded-full mix-blend-multiply filter blur-xl animate-pulse"></div>
        <div className="absolute top-0 right-0 w-72 h-72 bg-indigo-300 rounded-full mix-blend-multiply filter blur-xl animate-pulse animation-delay-2000"></div>
        <div className="absolute bottom-0 left-0 w-72 h-72 bg-cyan-300 rounded-full mix-blend-multiply filter blur-xl animate-pulse animation-delay-4000"></div>
      </div>

      <motion.div
        className="absolute top-0 left-0 right-0 h-2 bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-600"
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 2 }}
      />

      <div className="relative z-10 max-w-7xl mx-auto p-3 sm:p-4 md:p-6">
        <motion.div
          className="text-center mb-8 sm:mb-12 relative"
          initial={{ opacity: 0, y: -50 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
        >
          <div className="absolute inset-0 overflow-hidden">
            <motion.div
              className="absolute top-1/2 left-1/2 w-96 h-96 bg-gradient-to-r from-blue-500/20 to-indigo-500/20 rounded-full blur-3xl"
              animate={{
                scale: [1, 1.2, 1],
                rotate: [0, 180, 360],
              }}
              transition={{
                duration: 20,
                repeat: Number.POSITIVE_INFINITY,
                ease: "linear",
              }}
              style={{ transform: "translate(-50%, -50%)" }}
            />
          </div>

          <div className="relative z-10">
            <div className="flex items-center justify-center mb-6 sm:mb-8">
              <motion.div
                className="relative mr-4 sm:mr-6"
                animate={{ rotate: 360 }}
                transition={{ duration: 20, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
              >
                <div className="w-16 h-16 sm:w-20 sm:h-20 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-full flex items-center justify-center shadow-2xl border-4 border-white">
                  <GraduationCap className="w-8 h-8 sm:w-10 sm:h-10 text-white" />
                </div>
                <div className="absolute inset-0 w-16 h-16 sm:w-20 sm:h-20 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-full animate-ping opacity-20"></div>

                <motion.div
                  className="absolute top-1/2 left-1/2 w-24 h-24 sm:w-32 sm:h-32 border-2 border-blue-300/30 rounded-full"
                  style={{ transform: "translate(-50%, -50%)" }}
                  animate={{ rotate: -360 }}
                  transition={{ duration: 15, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
                >
                  <div className="absolute top-0 left-1/2 w-2 h-2 bg-blue-400 rounded-full transform -translate-x-1/2 -translate-y-1/2"></div>
                </motion.div>

                <motion.div
                  className="absolute top-1/2 left-1/2 w-32 h-32 sm:w-40 sm:h-40 border border-indigo-300/20 rounded-full"
                  style={{ transform: "translate(-50%, -50%)" }}
                  animate={{ rotate: 360 }}
                  transition={{ duration: 25, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
                >
                  <div className="absolute top-1/2 right-0 w-1.5 h-1.5 bg-indigo-400 rounded-full transform translate-x-1/2 -translate-y-1/2"></div>
                </motion.div>
              </motion.div>
            </div>

            <motion.h1
              className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold bg-gradient-to-r from-blue-700 via-indigo-600 to-blue-800 bg-clip-text text-transparent mb-4 sm:mb-6 tracking-tight"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.3, duration: 0.8 }}
            >
              SymbiSpark
              <motion.span
                className="block text-2xl sm:text-3xl md:text-4xl lg:text-5xl mt-2 bg-gradient-to-r from-indigo-600 to-blue-800 bg-clip-text text-transparent"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.6, duration: 0.8 }}
              >
                INTELLIGENT CAREER PLATFORM
              </motion.span>
            </motion.h1>

            <motion.div
              className="max-w-4xl mx-auto px-4"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.9, duration: 0.8 }}
            >
              <p className="text-lg sm:text-xl text-gray-700 mb-4">
                Advanced AI-powered career opportunities and interview preparation for technology professionals
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center space-y-2 sm:space-y-0 sm:space-x-8 text-sm text-gray-600">
                <div className="flex items-center">
                  <div className="w-2 h-2 bg-emerald-400 rounded-full mr-2 animate-pulse"></div>
                  <span>Smart Job Matching</span>
                </div>
                <div className="flex items-center">
                  <div className="w-2 h-2 bg-blue-400 rounded-full mr-2 animate-pulse"></div>
                  <span>Multi-Portal Integration</span>
                </div>
                <div className="flex items-center">
                  <div className="w-2 h-2 bg-indigo-400 rounded-full mr-2 animate-pulse"></div>
                  <span>Interview Preparation</span>
                </div>
              </div>
            </motion.div>
          </div>
        </motion.div>

        <motion.div
          className="flex items-center justify-center mb-6 sm:mb-8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
        >
          <div
            className={`flex items-center px-4 sm:px-6 py-2 sm:py-3 rounded-full backdrop-blur-md border-2 shadow-lg text-sm sm:text-base ${
              connectionStatus === "Quantum link established"
                ? "bg-emerald-50 border-emerald-400 text-emerald-700"
                : connectionStatus === "Establishing quantum link..."
                  ? "bg-blue-50 border-blue-400 text-blue-700"
                  : "bg-red-50 border-red-400 text-red-700"
            }`}
          >
            <motion.div
              animate={connectionStatus === "Quantum link established" ? { scale: [1, 1.2, 1] } : {}}
              transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY }}
            >
              {connectionStatus === "Quantum link established" ? (
                <Wifi className="w-4 h-4 sm:w-5 sm:h-5 mr-2 sm:mr-3" />
              ) : (
                <WifiOff className="w-4 h-4 sm:w-5 sm:h-5 mr-2 sm:mr-3" />
              )}
            </motion.div>
            <span className="font-bold">{connectionStatus}</span>
          </div>
        </motion.div>

        <motion.div
          className="bg-white/90 backdrop-blur-xl rounded-2xl sm:rounded-3xl border-2 border-blue-200 p-4 sm:p-6 md:p-8 mb-6 sm:mb-8 shadow-2xl"
          initial={{ opacity: 0, y: 50 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
        >
          <div className="flex mb-4 sm:mb-6">
            <motion.button
              className={`flex-1 px-4 sm:px-6 py-2 sm:py-3 rounded-r-xl font-bold text-base sm:text-lg ${
                activeTab === "interview"
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white"
                  : "bg-gray-200 text-gray-700"
              }`}
              onClick={() => setActiveTab("interview")}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              Interview Prep
            </motion.button>
            <motion.button
              className={`flex-1 px-4 sm:px-6 py-2 sm:py-3 rounded-l-xl font-bold text-base sm:text-lg ${
                activeTab === "jobs"
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white"
                  : "bg-gray-200 text-gray-700"
              }`}
              onClick={() => setActiveTab("jobs")}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              Job Search
            </motion.button>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 sm:gap-8">
            <motion.div whileHover={{ scale: 1.01 }} transition={{ type: "spring", stiffness: 300 }}>
              {activeTab === "jobs" ? (
                <>
                  <div className="bg-gradient-to-br from-blue-600 to-indigo-600 p-4 sm:p-6 rounded-xl sm:rounded-2xl text-white mb-4 sm:mb-6 shadow-xl">
                    <div className="flex items-center mb-3 sm:mb-4">
                      <Search className="w-6 h-6 sm:w-8 sm:h-8 mr-3 sm:mr-4" />
                      <h2 className="text-xl sm:text-2xl font-bold">INTELLIGENT JOB SEARCH</h2>
                    </div>
                    <p className="text-blue-100 text-base sm:text-lg">
                      Advanced AI-powered career matching for SIT professionals
                    </p>
                  </div>

                  <div className="space-y-4 sm:space-y-6">
                    <div>
                      <label className="block text-sm font-bold text-gray-700 mb-2 sm:mb-3 uppercase tracking-wide">
                        Target Role *
                      </label>
                      <input
                        type="text"
                        value={jobRole}
                        onChange={(e) => setJobRole(e.target.value)}
                        placeholder="e.g., AI Engineer, Machine Learning Engineer"
                        className="w-full px-3 sm:px-4 py-3 sm:py-4 border-2 border-blue-200 rounded-lg sm:rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white/90 backdrop-blur-sm text-base sm:text-lg font-semibold text-black"
                        list="job-suggestions"
                      />
                      <datalist id="job-suggestions">
                        {popularRoles.map((role) => (
                          <option key={role} value={role} />
                        ))}
                        {suggestions.map((s) => (
                          <option key={`s-${s}`} value={s} />
                        ))}
                      </datalist>
                    </div>

                    <div>
                      <label className="block text-sm font-bold text-gray-700 mb-2 sm:mb-3 uppercase tracking-wide">
                        Location
                      </label>
                      <select
                        value={location}
                        onChange={(e) => setLocation(e.target.value)}
                        className="w-full px-3 sm:px-4 py-3 sm:py-4 border-2 border-blue-200 rounded-lg sm:rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white/90 backdrop-blur-sm text-base sm:text-lg font-semibold text-black"
                      >
                        {indianCities.map((city) => (
                          <option key={city} value={city}>
                            {city}
                          </option>
                        ))}
                      </select>
                    </div>

                    {showFilters && (
                      <motion.div
                        className="grid grid-cols-1 gap-3 sm:gap-4 p-4 sm:p-6 bg-blue-50 rounded-xl sm:rounded-2xl border-2 border-blue-200"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3 }}
                      >
                        <div>
                          <label className="block text-sm font-bold text-gray-700 mb-2 uppercase tracking-wide">
                            Experience Level
                          </label>
                          <select
                            value={filters.experience_level}
                            onChange={(e) =>
                              setFilters((prev) => ({
                                ...prev,
                                experience_level: e.target.value,
                              }))
                            }
                            className="w-full px-3 py-2 sm:py-3 border-2 border-blue-200 rounded-lg focus:ring-2 focus:ring-blue-500 font-semibold text-sm sm:text-base"
                          >
                            <option value="entry">Entry Level</option>
                            <option value="fresher">Fresher</option>
                            <option value="intern">Internship</option>
                          </select>
                        </div>

                        <div>
                          <label className="block text-sm font-bold text-gray-700 mb-2 uppercase tracking-wide">
                            Job Type
                          </label>
                          <select
                            value={filters.job_type}
                            onChange={(e) => setFilters((prev) => ({ ...prev, job_type: e.target.value }))}
                            className="w-full px-3 py-2 sm:py-3 border-2 border-blue-200 rounded-lg focus:ring-2 focus:ring-blue-500 font-semibold text-sm sm:text-base"
                          >
                            <option value="all">All Types</option>
                            <option value="full-time">Full-time</option>
                            <option value="internship">Internship</option>
                            <option value="contract">Contract</option>
                          </select>
                        </div>

                        <div>
                          <label className="block text-sm font-bold text-gray-700 mb-2 uppercase tracking-wide">
                            Salary Range
                          </label>
                          <select
                            value={filters.salary_range}
                            onChange={(e) => setFilters((prev) => ({ ...prev, salary_range: e.target.value }))}
                            className="w-full px-3 py-2 sm:py-3 border-2 border-blue-200 rounded-lg focus:ring-2 focus:ring-blue-500 font-semibold text-sm sm:text-base"
                          >
                            <option value="all">Any Salary</option>
                            <option value="0-3">0-3 LPA</option>
                            <option value="3-6">3-6 LPA</option>
                            <option value="6-10">6-10 LPA</option>
                            <option value="10+">10+ LPA</option>
                          </select>
                        </div>
                      </motion.div>
                    )}

                    <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
                      <motion.button
                        onClick={searchJobs}
                        disabled={loading}
                        className="flex-1 px-6 sm:px-8 py-3 sm:py-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl sm:rounded-2xl font-bold hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 transition-all duration-300 border-2 border-blue-400 shadow-xl flex items-center justify-center text-sm sm:text-base"
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        {loading ? (
                          <Loader2 className="w-5 h-5 sm:w-6 sm:h-6 mr-2 sm:mr-3 animate-spin" />
                        ) : (
                          <Search className="w-5 h-5 sm:w-6 sm:h-6 mr-2 sm:mr-3" />
                        )}
                        {loading ? "PROCESSING..." : "START SEARCH"}
                      </motion.button>

                      <motion.button
                        onClick={() => setShowFilters(!showFilters)}
                        className="px-4 sm:px-6 py-3 sm:py-4 bg-slate-600 text-white rounded-xl sm:rounded-2xl font-bold hover:bg-slate-700 transition-all duration-300 border-2 border-slate-500 shadow-xl flex items-center justify-center text-sm sm:text-base"
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        <Filter className="w-4 h-4 sm:w-5 sm:h-5 mr-1 sm:mr-2" />
                        {showFilters ? "HIDE FILTERS" : "SHOW FILTERS"}
                      </motion.button>
                    </div>

                    <div className="mt-4 sm:mt-6">
                      <p className="text-sm font-bold text-gray-700 mb-2 sm:mb-3 uppercase tracking-wide">
                        Popular Technology Roles:
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {popularRoles.slice(0, 6).map((role) => (
                          <button
                            key={role}
                            onClick={() => setJobRole(role)}
                            className="px-3 py-1.5 sm:px-4 sm:py-2 bg-blue-100 text-blue-700 rounded-full text-xs sm:text-sm hover:bg-blue-200 transition-colors font-semibold border border-blue-300"
                          >
                            {role}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="bg-gradient-to-br from-blue-600 to-indigo-600 p-4 sm:p-6 rounded-xl sm:rounded-2xl text-white mb-4 sm:mb-6 shadow-xl">
                    <div className="flex items-center mb-3 sm:mb-4">
                      <FileText className="w-6 h-6 sm:w-8 sm:h-8 mr-3 sm:mr-4" />
                      <h2 className="text-xl sm:text-2xl font-bold">INTERVIEW QUESTION SEARCH</h2>
                    </div>
                    <p className="text-blue-100 text-base sm:text-lg">
                      Find India-specific interview questions for your domain
                    </p>
                  </div>

                  <div className="space-y-4 sm:space-y-6">
                    <div>
                      <label className="block text-sm font-bold text-gray-700 mb-2 sm:mb-3 uppercase tracking-wide">
                        Domain *
                      </label>
                      <select
                        value={interviewDomain}
                        onChange={(e) => setInterviewDomain(e.target.value)}
                        className="w-full px-3 sm:px-4 py-3 sm:py-4 border-2 border-blue-200 rounded-lg sm:rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white/90 backdrop-blur-sm text-base sm:text-lg font-semibold text-black"
                      >
                        <option value="">Select a domain</option>
                        {popularDomains.map((domain) => (
                          <option key={domain} value={domain}>
                            {domain}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-bold text-gray-700 mb-2 sm:mb-3 uppercase tracking-wide">
                        Company
                      </label>
                      <input
                        type="text"
                        value={interviewCompany}
                        onChange={(e) => setInterviewCompany(e.target.value)}
                        placeholder="e.g., Barclays, TCS, Infosys"
                        className="w-full px-3 sm:px-4 py-3 sm:py-4 border-2 border-blue-200 rounded-lg sm:rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white/90 backdrop-blur-sm text-base sm:text-lg font-semibold text-black"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-bold text-gray-700 mb-2 sm:mb-3 uppercase tracking-wide">
                        Difficulty
                      </label>
                      <select
                        value={difficultyFilter}
                        onChange={(e) => setDifficultyFilter(e.target.value)}
                        className="w-full px-3 sm:px-4 py-3 sm:py-4 border-2 border-blue-200 rounded-lg sm:rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white/90 backdrop-blur-sm text-base sm:text-lg font-semibold text-black"
                      >
                        <option value="all">All Difficulties</option>
                        <option value="easy">Easy</option>
                        <option value="medium">Medium</option>
                        <option value="hard">Hard</option>
                      </select>
                    </div>

                    <motion.button
                      onClick={searchInterviewQuestions}
                      disabled={interviewLoading}
                      className="w-full px-6 sm:px-8 py-3 sm:py-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl sm:rounded-2xl font-bold hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 transition-all duration-300 border-2 border-blue-400 shadow-xl flex items-center justify-center text-sm sm:text-base"
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      {interviewLoading ? (
                        <Loader2 className="w-5 h-5 sm:w-6 sm:h-6 mr-2 sm:mr-3 animate-spin" />
                      ) : (
                        <FileText className="w-5 h-5 sm:w-6 sm:h-6 mr-2 sm:mr-3" />
                      )}
                      {interviewLoading ? "PROCESSING..." : "FIND QUESTIONS"}
                    </motion.button>
                  </div>
                </>
              )}
            </motion.div>

            <motion.div
              className="relative flex justify-center items-start"
              initial={{ opacity: 0, x: 50 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8, delay: 0.4 }}
            >
              {/* Mobile logs toggle button */}
              <div className="xl:hidden w-full mb-4">
                <motion.button
                  onClick={() => setShowMobileLogs(!showMobileLogs)}
                  className="w-full px-4 py-3 bg-slate-800 text-white rounded-xl font-bold hover:bg-slate-700 transition-all duration-300 border-2 border-slate-600 shadow-xl flex items-center justify-center"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {showMobileLogs ? <X className="w-5 h-5 mr-2" /> : <Menu className="w-5 h-5 mr-2" />}
                  {showMobileLogs ? "HIDE LOGS" : "SHOW SYSTEM LOGS"}
                </motion.button>
              </div>

              {/* Desktop phone mockup - hidden on mobile */}
              <div className="hidden xl:block relative w-[350px] h-[650px] bg-slate-900 rounded-[40px] p-3 shadow-2xl border-4 border-slate-700">
                <div className="absolute top-0 left-1/2 transform -translate-x-1/2 w-1/3 h-7 bg-slate-900 rounded-b-xl z-10"></div>
                <div className="absolute -left-1 top-[120px] w-1 h-12 bg-slate-600 rounded-l-lg"></div>
                <div className="absolute -left-1 top-[150px] w-1 h-12 bg-slate-600 rounded-l-lg"></div>
                <div className="absolute -right-1 top-[100px] w-1 h-16 bg-slate-600 rounded-r-lg"></div>

                <div className="w-full h-full bg-gradient-to-b from-slate-800 via-slate-900 to-black rounded-[32px] overflow-hidden relative border-2 border-blue-400">
                  <div className="bg-gradient-to-r from-blue-700 via-indigo-700 to-blue-800 p-4 border-b-2 border-blue-400 shadow-lg">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <motion.div
                          className={`w-4 h-4 rounded-full mr-3 shadow-lg border border-white ${
                            loading || interviewLoading ? "bg-emerald-400 shadow-emerald-400/50" : "bg-slate-400"
                          }`}
                          animate={
                            loading || interviewLoading
                              ? {
                                  scale: [1, 1.4, 1],
                                  opacity: [1, 0.6, 1],
                                }
                              : {}
                          }
                          transition={{ duration: 1.5, repeat: Number.POSITIVE_INFINITY }}
                        />
                        <div>
                          <div className="font-bold text-white text-sm">SIT CAREER PLATFORM</div>
                          <div className="text-xs text-blue-200">Professional Search Terminal</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 h-full overflow-hidden">
                    <div className="h-full overflow-y-auto space-y-2 scrollbar-thin scrollbar-thumb-blue-500">
                      <AnimatePresence>
                        {thoughts.map((thought, index) => (
                          <motion.div
                            key={index}
                            className="text-xs font-mono"
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ duration: 0.3 }}
                          >
                            <div className="flex items-start space-x-2">
                              <span className="text-blue-400 font-bold">[{formatTimestamp(thought.timestamp)}]</span>
                              <span className={`font-bold ${getAgentColor(thought.agent).split(" ")[0]}`}>
                                {thought.agent}:
                              </span>
                              <span className="text-emerald-400 flex-1">{thought.message}</span>
                            </div>
                          </motion.div>
                        ))}
                      </AnimatePresence>
                      <div ref={thoughtsEndRef} />
                    </div>
                  </div>
                </div>
              </div>

              <AnimatePresence>
                {showMobileLogs && (
                  <motion.div
                    className="xl:hidden w-full bg-slate-900 rounded-2xl border-4 border-slate-700 shadow-2xl overflow-hidden"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "400px" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.3 }}
                  >
                    <div className="bg-gradient-to-r from-blue-700 via-indigo-700 to-blue-800 p-4 border-b-2 border-blue-400 shadow-lg">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center">
                          <motion.div
                            className={`w-4 h-4 rounded-full mr-3 shadow-lg border border-white ${
                              loading || interviewLoading ? "bg-emerald-400 shadow-emerald-400/50" : "bg-slate-400"
                            }`}
                            animate={
                              loading || interviewLoading
                                ? {
                                    scale: [1, 1.4, 1],
                                    opacity: [1, 0.6, 1],
                                  }
                                : {}
                            }
                            transition={{ duration: 1.5, repeat: Number.POSITIVE_INFINITY }}
                          />
                          <div>
                            <div className="font-bold text-white text-sm">SIT CAREER PLATFORM</div>
                            <div className="text-xs text-blue-200">Professional Search Terminal</div>
                          </div>
                        </div>
                        <button
                          onClick={() => setShowMobileLogs(false)}
                          className="text-white hover:text-blue-200 transition-colors"
                        >
                          <X className="w-5 h-5" />
                        </button>
                      </div>
                    </div>

                    <div className="p-4 h-full overflow-hidden bg-gradient-to-b from-slate-800 via-slate-900 to-black">
                      <div className="h-full overflow-y-auto space-y-2 scrollbar-thin scrollbar-thumb-blue-500">
                        <AnimatePresence>
                          {thoughts.map((thought, index) => (
                            <motion.div
                              key={index}
                              className="text-sm font-mono leading-relaxed"
                              initial={{ opacity: 0, x: -20 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ duration: 0.3 }}
                            >
                              <div className="flex flex-col space-y-1 p-2 bg-slate-800/50 rounded-lg">
                                <div className="flex items-center space-x-2">
                                  <span className="text-blue-400 font-bold text-xs">
                                    [{formatTimestamp(thought.timestamp)}]
                                  </span>
                                  <span className={`font-bold text-xs ${getAgentColor(thought.agent).split(" ")[0]}`}>
                                    {thought.agent}
                                  </span>
                                </div>
                                <span className="text-emerald-400 text-sm break-words">{thought.message}</span>
                              </div>
                            </motion.div>
                          ))}
                        </AnimatePresence>
                        <div ref={thoughtsEndRef} />
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          </div>

          <AnimatePresence>
            <motion.div
              className="mt-4 sm:mt-6 p-4 sm:p-6 rounded-xl sm:rounded-2xl bg-slate-50 border-2 border-slate-200"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <div className="flex items-center">
                {error ? (
                  <AlertCircle className="w-5 h-5 sm:w-6 sm:h-6 text-red-500 mr-2 sm:mr-3 flex-shrink-0" />
                ) : status.includes("completed") ? (
                  <CheckCircle className="w-5 h-5 sm:w-6 sm:h-6 text-emerald-500 mr-2 sm:mr-3 flex-shrink-0" />
                ) : (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
                  >
                    <Activity className="w-5 h-5 sm:w-6 sm:h-6 text-blue-500 mr-2 sm:mr-3 flex-shrink-0" />
                  </motion.div>
                )}
                <p
                  className={`font-bold text-sm sm:text-lg break-words ${
                    error ? "text-red-600" : status.includes("completed") ? "text-emerald-600" : "text-blue-600"
                  }`}
                >
                  {error || status}
                </p>
              </div>
            </motion.div>
          </AnimatePresence>

          {error && (
            <motion.div
              className="mt-3 sm:mt-4 p-3 sm:p-4 bg-red-50 text-red-700 rounded-lg flex items-start border-2 border-red-200"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5 }}
            >
              <AlertCircle className="w-4 h-4 sm:w-5 sm:h-5 mr-2 flex-shrink-0 mt-0.5" />
              <span className="text-sm sm:text-base break-words">{error}</span>
            </motion.div>
          )}
        </motion.div>

        <div className="grid grid-cols-1 gap-6 sm:gap-8">
          {activeTab === "jobs" ? (
            <AnimatePresence>
              {searchResults && (
                <motion.div
                  className="bg-white/95 backdrop-blur-xl rounded-2xl sm:rounded-3xl border-2 border-blue-200 overflow-hidden shadow-2xl"
                  initial={{ opacity: 0, y: 50 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.8, delay: 0.6 }}
                >
                  <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-4 sm:p-6 border-b-2 border-blue-300">
                    <h2 className="text-2xl sm:text-3xl font-bold text-white flex items-center">
                      <Shield className="w-6 h-6 sm:w-8 sm:h-8 mr-3 sm:mr-4 text-white" />
                      PROFESSIONAL OPPORTUNITIES
                    </h2>
                    <p className="text-blue-100 mt-2 text-base sm:text-lg font-semibold">
                      {searchResults.total_jobs} high-quality positions identified
                    </p>
                  </div>

                  <AnimatePresence mode="wait">
                    {showCandidatesAnimation ? (
                      <motion.div
                        className="flex items-center justify-center py-16 sm:py-24"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        key="loading"
                      >
                        <div className="text-center">
                          <motion.div
                            className="w-16 h-16 sm:w-20 sm:h-20 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4 sm:mb-6"
                            animate={{ rotate: 360 }}
                            transition={{ duration: 1, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
                          />
                          <motion.h3
                            className="text-xl sm:text-2xl font-bold text-gray-800 mb-2"
                            animate={{ opacity: [0.5, 1, 0.5] }}
                            transition={{ duration: 1.5, repeat: Number.POSITIVE_INFINITY }}
                          >
                            ANALYSIS COMPLETE
                          </motion.h3>
                          <p className="text-blue-600 font-semibold text-sm sm:text-base">
                            Presenting career opportunities...
                          </p>
                        </div>
                      </motion.div>
                    ) : searchResults.total_jobs === 0 ? (
                      <motion.div
                        className="text-center py-16 sm:py-20 px-4 sm:px-6"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        key="empty"
                      >
                        <motion.div
                          className="w-20 h-20 sm:w-24 sm:h-24 bg-gradient-to-br from-blue-200 to-indigo-200 rounded-full flex items-center justify-center mx-auto mb-6 sm:mb-8"
                          animate={{ scale: [1, 1.1, 1] }}
                          transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY }}
                        >
                          <Search className="w-10 h-10 sm:w-12 sm:h-12 text-blue-600" />
                        </motion.div>
                        <h3 className="text-xl sm:text-2xl font-bold text-gray-800 mb-3 sm:mb-4">NO MATCHES FOUND</h3>
                        <p className="text-gray-600 text-base sm:text-lg">
                          Try adjusting your search criteria or explore different job roles
                        </p>
                      </motion.div>
                    ) : (
                      <motion.div
                        className="p-4 sm:p-6 space-y-4 sm:space-y-6 max-h-[800px] overflow-y-auto"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ duration: 0.5 }}
                        key="jobs"
                      >
                        {searchResults.all_jobs.map((job, index) => (
                          <JobCard key={index} job={job} index={index} />
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              )}
            </AnimatePresence>
          ) : (
            <AnimatePresence>
              {interviewLoading ? (
                <motion.div
                  className="flex items-center justify-center py-16 sm:py-24"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  key="loading"
                >
                  <div className="text-center">
                    <motion.div
                      className="w-16 h-16 sm:w-20 sm:h-20 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4 sm:mb-6"
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
                    />
                    <motion.h3
                      className="text-xl sm:text-2xl font-bold text-gray-800 mb-2"
                      animate={{ opacity: [0.5, 1, 0.5] }}
                      transition={{ duration: 1.5, repeat: Number.POSITIVE_INFINITY }}
                    >
                      FETCHING QUESTIONS
                    </motion.h3>
                    <p className="text-blue-600 font-semibold text-sm sm:text-base">Analyzing interview questions...</p>
                  </div>
                </motion.div>
              ) : interviewResults ? (
                <motion.div
                  className="bg-white/95 backdrop-blur-xl rounded-2xl sm:rounded-3xl border-2 border-blue-200 overflow-hidden shadow-2xl"
                  initial={{ opacity: 0, y: 50 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.8, delay: 0.6 }}
                >
                  <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-4 sm:p-6 border-b-2 border-blue-300">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 sm:gap-0">
                      <h2 className="text-2xl sm:text-3xl font-bold text-white flex items-center">
                        <FileText className="w-6 h-6 sm:w-8 sm:h-8 mr-3 sm:mr-4 text-white" />
                        INTERVIEW QUESTIONS
                      </h2>
                      <motion.button
                        onClick={downloadPDF}
                        className="px-4 sm:px-6 py-2 sm:py-3 bg-white text-blue-600 rounded-lg sm:rounded-xl font-bold hover:bg-blue-100 transition-all duration-300 border-2 border-blue-400 shadow-lg flex items-center text-sm sm:text-base"
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        <FileText className="w-4 h-4 sm:w-5 sm:h-5 mr-1 sm:mr-2" />
                        DOWNLOAD PDF
                      </motion.button>
                    </div>
                    <p className="text-blue-100 mt-2 text-base sm:text-lg font-semibold">
                      {interviewResults.total_questions} questions for {interviewResults.domain}
                      {interviewResults.company && ` at ${interviewResults.company}`}
                    </p>
                    {interviewResults.search_metadata ? (
                      <p className="text-blue-100 text-xs sm:text-sm">
                        Sources searched: {interviewResults.search_metadata.sources_searched || 0} | Queries used:{" "}
                        {interviewResults.search_metadata.search_queries_used || 0}
                      </p>
                    ) : (
                      <p className="text-blue-100 text-xs sm:text-sm">Metadata unavailable</p>
                    )}
                  </div>

                  <motion.div
                    className="p-4 sm:p-6 space-y-4 sm:space-y-6 max-h-[800px] overflow-y-auto"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.5 }}
                    key="questions"
                  >
                    {interviewResults.questions.length === 0 ? (
                      <motion.div
                        className="text-center py-16 sm:py-20 px-4 sm:px-6"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        key="empty"
                      >
                        <motion.div
                          className="w-20 h-20 sm:w-24 sm:h-24 bg-gradient-to-br from-blue-200 to-indigo-200 rounded-full flex items-center justify-center mx-auto mb-6 sm:mb-8"
                          animate={{ scale: [1, 1.1, 1] }}
                          transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY }}
                        >
                          <FileText className="w-10 h-10 sm:w-12 sm:h-12 text-blue-600" />
                        </motion.div>
                        <h3 className="text-xl sm:text-2xl font-bold text-gray-800 mb-3 sm:mb-4">NO QUESTIONS FOUND</h3>
                        <p className="text-gray-600 text-base sm:text-lg">
                          Try adjusting your domain or company criteria
                        </p>
                      </motion.div>
                    ) : (
                      interviewResults.questions.map((question, index) => (
                        <InterviewQuestionCard key={index} question={question} index={index} />
                      ))
                    )}
                  </motion.div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          )}
        </div>

        {activeTab === "jobs" && savedJobs.length > 0 && (
          <motion.div
            className="mt-6 sm:mt-8 bg-white/95 backdrop-blur-xl rounded-2xl sm:rounded-3xl border-2 border-blue-200 overflow-hidden shadow-2xl"
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
          >
            <div className="bg-gradient-to-r from-indigo-600 to-blue-600 p-4 sm:p-6 border-b-2 border-indigo-300">
              <h2 className="text-2xl sm:text-3xl font-bold text-white flex items-center">
                <Bookmark className="w-6 h-6 sm:w-8 sm:h-8 mr-3 sm:mr-4 text-white" />
                SAVED OPPORTUNITIES ({savedJobs.length})
              </h2>
            </div>
            <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
              {savedJobs.map((job, index) => (
                <JobCard key={index} job={job} index={index} />
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  )
}
