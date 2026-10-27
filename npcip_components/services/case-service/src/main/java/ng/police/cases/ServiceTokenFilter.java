package ng.police.cases;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
@Component
public class ServiceTokenFilter extends OncePerRequestFilter {
    private final String expected;
    public ServiceTokenFilter(@Value("${npcip.service-token:}") String expected) { this.expected = expected; }
    @Override protected boolean shouldNotFilter(HttpServletRequest request) {
        return request.getRequestURI().startsWith("/actuator/health") || !request.getRequestURI().startsWith("/internal/");
    }
    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) throws ServletException, IOException {
        String provided = request.getHeader("X-NPCIP-Service-Token");
        if (expected == null || expected.isBlank() || provided == null ||
            !MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8), provided.getBytes(StandardCharsets.UTF_8))) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            response.getWriter().write("{\"error\":\"internal-service-authentication-required\"}");
            return;
        }
        chain.doFilter(request, response);
    }
}
