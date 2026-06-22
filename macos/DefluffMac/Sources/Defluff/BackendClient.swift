import Foundation

struct SubmittedURL: Decodable {
    let id: Int
    let url: String
    let status: String
    let createdAt: Date
    let updatedAt: Date

    private enum CodingKeys: String, CodingKey {
        case id
        case url
        case status
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct CaptionResponse: Decodable {
    let url: String
    let title: String?
    let language: String
    let source: String
    let text: String
    let segments: [CaptionSegment]
}

struct CaptionSegment: Decodable, Identifiable {
    let start: Double
    let end: Double
    let text: String

    var id: String {
        "\(start)-\(end)-\(text)"
    }
}

struct ContentResponse: Decodable {
    let url: String
    let title: String?
    let kind: String
    let source: String
    let text: String
    let language: String?
    let segments: [CaptionSegment]
    let media: [ContentMedia]
    let blocks: [ContentBlock]
}

struct ContentBlock: Decodable {
    let kind: String
    let text: String?
    let media: ContentMedia?
}

struct ContentMedia: Decodable, Identifiable {
    let kind: String
    let url: String
    let alt: String?
    let caption: String?

    var id: String {
        url
    }
}

struct ConsumeResponse: Decodable {
    let content: ContentResponse
    let analysis: ConsumptionAnalysis
    let researchResults: [ResearchResult]
    let researchDocuments: [ResearchDocument]
    let knowledgeMatches: [KnowledgeMatch]
    let agentTraces: [AgentTrace]

    private enum CodingKeys: String, CodingKey {
        case content
        case analysis
        case researchResults = "research_results"
        case researchDocuments = "research_documents"
        case knowledgeMatches = "knowledge_matches"
        case agentTraces = "agent_traces"
    }
}

struct ConsumeStreamEvent: Decodable {
    let type: String
    let trace: AgentTrace?
    let result: ResearchResult?
    let content: ContentResponse?
    let analysis: ConsumptionAnalysis?
    let highlight: Highlight?
    let chapter: Chapter?
    let response: ConsumeResponse?
    let message: String?
}

struct ConsumptionAnalysis: Decodable {
    let summary: String
    let summaryPoints: [String]
    let tldr: String?
    let reasoningSummary: String?
    let readingFlow: [String]
    let contextHelpers: [String]
    let glossary: [TermExplanation]
    let visualAids: [VisualAid]
    let researchContext: [String]
    let researchHighlights: [ResearchHighlight]
    let deepDiveQuestions: [String]
    let keyPoints: [String]
    let novelPoints: [String]
    let alreadyKnown: [String]
    let highlights: [Highlight]
    let chapters: [Chapter]

    private enum CodingKeys: String, CodingKey {
        case summary
        case summaryPoints = "summary_points"
        case tldr
        case reasoningSummary = "reasoning_summary"
        case readingFlow = "reading_flow"
        case contextHelpers = "context_helpers"
        case glossary
        case visualAids = "visual_aids"
        case researchContext = "research_context"
        case researchHighlights = "research_highlights"
        case deepDiveQuestions = "deep_dive_questions"
        case keyPoints = "key_points"
        case novelPoints = "novel_points"
        case alreadyKnown = "already_known"
        case highlights
        case chapters
    }
}

struct ResearchHighlight: Decodable, Identifiable {
    let title: String
    let url: String
    let point: String
    let whyItMatters: String

    private enum CodingKeys: String, CodingKey {
        case title
        case url
        case point
        case whyItMatters = "why_it_matters"
    }

    var id: String {
        "\(url)-\(point)"
    }
}

struct TermExplanation: Decodable, Identifiable {
    let term: String
    let explanation: String

    var id: String {
        term
    }
}

struct VisualAid: Decodable, Identifiable {
    let title: String
    let explanation: String
    let imageURL: String?
    let imageAlt: String?
    let suggestedDiagram: String?

    private enum CodingKeys: String, CodingKey {
        case title
        case explanation
        case imageURL = "image_url"
        case imageAlt = "image_alt"
        case suggestedDiagram = "suggested_diagram"
    }

    var id: String {
        imageURL ?? suggestedDiagram ?? title
    }
}

struct Highlight: Decodable, Identifiable {
    let text: String
    let why: String
    let summary: String?
    let caption: String?
    let start: Double?
    let end: Double?
    let timestamp: String?
    let endTimestamp: String?

    private enum CodingKeys: String, CodingKey {
        case text
        case why
        case summary
        case caption
        case start
        case end
        case timestamp
        case endTimestamp = "end_timestamp"
    }

    var id: String {
        "\(timestamp ?? "article")-\(text)-\(why)"
    }

    var cleanSummary: String? {
        if let summary, !summary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return summary
        }
        return nil
    }

    /// Display label like "00:12 – 00:18", or just the start when no end exists.
    var timeRange: String? {
        guard let timestamp else { return nil }
        if let endTimestamp, endTimestamp != timestamp {
            return "\(timestamp) – \(endTimestamp)"
        }
        return timestamp
    }
}

struct Chapter: Decodable, Identifiable {
    let title: String
    let summary: String
    let caption: String?
    let start: Double?
    let end: Double?
    let timestamp: String?
    let endTimestamp: String?

    private enum CodingKeys: String, CodingKey {
        case title
        case summary
        case caption
        case start
        case end
        case timestamp
        case endTimestamp = "end_timestamp"
    }

    var id: String {
        "\(timestamp ?? title)-\(title)"
    }

    var timeRange: String? {
        guard let timestamp else { return nil }
        if let endTimestamp, endTimestamp != timestamp {
            return "\(timestamp) – \(endTimestamp)"
        }
        return timestamp
    }
}

struct ResearchResult: Decodable, Identifiable {
    let title: String
    let url: String
    let snippet: String?
    let source: String?
    let query: String?

    var id: String {
        url
    }
}

struct ResearchDocument: Decodable, Identifiable {
    let title: String?
    let url: String
    let query: String?
    let source: String?
    let depth: Int
    let parentURL: String?
    let textExcerpt: String
    let outboundLinks: [ResearchResult]

    private enum CodingKeys: String, CodingKey {
        case title
        case url
        case query
        case source
        case depth
        case parentURL = "parent_url"
        case textExcerpt = "text_excerpt"
        case outboundLinks = "outbound_links"
    }

    var id: String {
        url
    }
}

struct AgentTrace: Decodable, Identifiable {
    let name: String
    let status: String
    let summary: String
    let details: [String]

    var id: String {
        name
    }
}

struct KnowledgeMatch: Decodable, Identifiable {
    let id: Int
    let url: String
    let title: String?
    let summary: String
    let consumedAt: Date
    let overlap: Double

    private enum CodingKeys: String, CodingKey {
        case id
        case url
        case title
        case summary
        case consumedAt = "consumed_at"
        case overlap
    }
}

struct DiscussEvent: Decodable {
    let type: String
    let text: String?
    let message: String?
}

enum BackendClientError: LocalizedError {
    case invalidBaseURL
    case invalidResponse
    case requestFailed(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL:
            return "The backend URL is invalid."
        case .invalidResponse:
            return "The backend returned an invalid response."
        case .requestFailed(let statusCode, let body):
            return "Backend request failed with status \(statusCode): \(body)"
        }
    }
}

struct BackendClient: Sendable {
    static let defaultBaseURL = URL(string: "http://127.0.0.1:8000")!

    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func submit(url: URL, baseURL: URL = Self.defaultBaseURL) async throws -> SubmittedURL {
        let endpoint = baseURL.appending(path: "api/urls")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["url": url.absoluteString])

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendClientError.invalidResponse
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw BackendClientError.requestFailed(httpResponse.statusCode, body)
        }

        return try Self.responseDecoder.decode(SubmittedURL.self, from: data)
    }

    func captions(url: URL, baseURL: URL = Self.defaultBaseURL) async throws -> CaptionResponse {
        let endpoint = baseURL.appending(path: "api/captions")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["url": url.absoluteString])

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendClientError.invalidResponse
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw BackendClientError.requestFailed(httpResponse.statusCode, body)
        }

        return try Self.responseDecoder.decode(CaptionResponse.self, from: data)
    }

    func content(url: URL, baseURL: URL = Self.defaultBaseURL) async throws -> ContentResponse {
        let endpoint = baseURL.appending(path: "api/content")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["url": url.absoluteString])

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendClientError.invalidResponse
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw BackendClientError.requestFailed(httpResponse.statusCode, body)
        }

        return try Self.responseDecoder.decode(ContentResponse.self, from: data)
    }

    func consume(url: URL, baseURL: URL = Self.defaultBaseURL) async throws -> ConsumeResponse {
        let endpoint = baseURL.appending(path: "api/consume")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["url": url.absoluteString])

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendClientError.invalidResponse
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw BackendClientError.requestFailed(httpResponse.statusCode, body)
        }

        return try Self.responseDecoder.decode(ConsumeResponse.self, from: data)
    }

    func consumeStream(
        url: URL,
        baseURL: URL = Self.defaultBaseURL
    ) async throws -> AsyncThrowingStream<ConsumeStreamEvent, Error> {
        let endpoint = baseURL.appending(path: "api/consume/stream")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["url": url.absoluteString])

        let (bytes, response) = try await session.bytes(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendClientError.invalidResponse
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            throw BackendClientError.requestFailed(httpResponse.statusCode, "")
        }

        return AsyncThrowingStream { continuation in
            Task {
                do {
                    for try await line in bytes.lines {
                        guard !line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                            continue
                        }

                        guard let data = line.data(using: .utf8) else {
                            continue
                        }

                        let event = try Self.responseDecoder.decode(ConsumeStreamEvent.self, from: data)
                        AppDebugLog.write(
                            "stream.event",
                            fields: [
                                "type": event.type,
                                "trace": event.trace?.name ?? "",
                                "message": event.message ?? ""
                            ]
                        )
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    func learn(
        kind: String,
        sourceURL: String,
        sourceTitle: String?,
        title: String,
        summary: String,
        detail: String?,
        baseURL: URL = Self.defaultBaseURL
    ) async throws {
        let endpoint = baseURL.appending(path: "api/knowledge/learn")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = [
            "kind": kind,
            "source_url": sourceURL,
            "title": title,
            "summary": summary,
        ]
        if let sourceTitle { body["source_title"] = sourceTitle }
        if let detail, !detail.isEmpty { body["detail"] = detail }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendClientError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw BackendClientError.requestFailed(httpResponse.statusCode, body)
        }
    }

    func discussStream(
        question: String,
        context: String,
        title: String?,
        history: [[String: String]],
        baseURL: URL = Self.defaultBaseURL
    ) async throws -> AsyncThrowingStream<DiscussEvent, Error> {
        let endpoint = baseURL.appending(path: "api/discuss/stream")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = ["question": question, "context": context, "history": history]
        if let title {
            body["title"] = title
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (bytes, response) = try await session.bytes(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendClientError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw BackendClientError.requestFailed(httpResponse.statusCode, "")
        }

        return AsyncThrowingStream { continuation in
            Task {
                do {
                    for try await line in bytes.lines {
                        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !trimmed.isEmpty, let data = trimmed.data(using: .utf8) else {
                            continue
                        }
                        let event = try Self.responseDecoder.decode(DiscussEvent.self, from: data)
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    private static var responseDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)

            let fractionalFormatter = ISO8601DateFormatter()
            fractionalFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = fractionalFormatter.date(from: value) {
                return date
            }

            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: value) {
                return date
            }

            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Invalid ISO8601 date: \(value)"
            )
        }
        return decoder
    }
}
