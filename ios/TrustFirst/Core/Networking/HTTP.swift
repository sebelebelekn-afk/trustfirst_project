import Foundation

/// Everything the app knows about a request that failed, in a form a screen can
/// actually show a person. `message` is safe to display; the rest is for logs.
struct HTTPError: LocalizedError {
    let status: Int
    let message: String
    let body: String?

    var errorDescription: String? { message }

    /// Server error payloads across this backend are one of two shapes:
    /// Django's `{"error": "..."}` or Supabase's `{"message": "..."}`. Pull
    /// whichever is there so the user sees the real reason rather than a code.
    static func from(status: Int, data: Data) -> HTTPError {
        let text = String(data: data, encoding: .utf8)
        if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            for key in ["error", "message", "msg", "error_description"] {
                if let message = object[key] as? String, !message.isEmpty {
                    return HTTPError(status: status, message: message, body: text)
                }
            }
        }
        return HTTPError(status: status, message: Self.generic(for: status), body: text)
    }

    private static func generic(for status: Int) -> String {
        switch status {
        case 401, 403: "You are not signed in, or not allowed to do that."
        case 404:      "That is not there any more."
        case 408, 504: "The server took too long to answer."
        case 429:      "Too many tries. Wait a moment and try again."
        case 500...:   "Something went wrong on our side."
        default:       "That did not work."
        }
    }
}

/// A small JSON-over-HTTP client. Deliberately hand-rolled and dependency-free:
/// every endpoint this app talks to — Django, PostgREST, GoTrue — is plain REST
/// with headers, and a bespoke client means no package to resolve, no version
/// to pin, and nothing between us and the wire when something misbehaves.
struct HTTP: Sendable {
    var session: URLSession = .shared

    /// Dates arrive from Postgres as ISO-8601, sometimes with fractional
    /// seconds and sometimes without. Accept both; one decoder for the app.
    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { source in
            let text = try source.singleValueContainer().decode(String.self)
            if let date = iso8601Fractional.date(from: text) { return date }
            if let date = iso8601Plain.date(from: text) { return date }
            throw DecodingError.dataCorruptedError(
                in: try source.singleValueContainer(),
                debugDescription: "Not an ISO-8601 date: \(text)"
            )
        }
        return decoder
    }()

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    // Configured once here and never mutated again. Foundation's date
    // formatters are thread-safe for parsing, so concurrent decodes are fine;
    // nonisolated(unsafe) is that guarantee stated to the compiler, which
    // cannot see it for itself.
    nonisolated(unsafe) private static let iso8601Fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    nonisolated(unsafe) private static let iso8601Plain: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    func send(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw HTTPError(status: -1, message: "No response from the server.", body: nil)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw HTTPError.from(status: http.statusCode, data: data)
        }
        return data
    }

    func send<T: Decodable>(_ request: URLRequest, as type: T.Type) async throws -> T {
        let data = try await send(request)
        do {
            return try Self.decoder.decode(T.self, from: data)
        } catch {
            // A decode failure means the server's shape moved, which is worth
            // saying out loud rather than reporting as a generic failure.
            throw HTTPError(
                status: 200,
                message: "The server sent back something this version does not understand.",
                body: String(data: data, encoding: .utf8)
            )
        }
    }
}

extension URLRequest {
    /// A request with no body — GET, or a POST that carries everything in the URL.
    static func json(
        _ method: String,
        url: URL,
        headers: [String: String] = [:]
    ) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }
        return request
    }

    /// A request that sends a JSON body.
    static func json(
        _ method: String,
        url: URL,
        headers: [String: String] = [:],
        body: some Encodable
    ) throws -> URLRequest {
        var request = json(method, url: url, headers: headers)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try HTTP.encoder.encode(body)
        return request
    }
}
