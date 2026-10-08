import os
import re

file_path = "/home/ubuntu/civiclens/admin-portal/src/App.jsx"

with open(file_path, "r") as f:
    content = f.read()

# 1. Update onLoginSuccess to capture the token
content = re.sub(
    r'onLoginSuccess=\{\(\) => \{[^\}]*?localStorage\.setItem\(\'isAdminAuthenticated\', \'true\'\);[^\}]*?setIsAuthenticated\(true\);[^\}]*?\}\}',
    r"onLoginSuccess={(token) => {\n                localStorage.setItem('adminToken', token);\n                localStorage.setItem('isAdminAuthenticated', 'true');\n                setIsAuthenticated(true);\n            }}",
    content,
    flags=re.DOTALL
)

# 2. Add the window.fetch interceptor inside the main App() component
interceptor_code = """
  React.useEffect(() => {
    if (isAuthenticated) {
      const token = localStorage.getItem('adminToken');
      const originalFetch = window.fetch;
      
      window.fetch = async (url, options = {}) => {
        // Only intercept backend API calls starting with /admin or /auth (if needed)
        if (typeof url === 'string' && (url.startsWith('/admin') || url.startsWith('/api'))) {
          options.headers = {
            ...options.headers,
            'Authorization': `Bearer ${token}`
          };
        }
        
        const response = await originalFetch(url, options);
        
        // Zero-vulnerability fallback: Auto-logout on 401 Unauthorized
        if (response.status === 401) {
            console.warn("Security Token Expired or Invalid. Logging out.");
            localStorage.clear();
            sessionStorage.clear();
            window.location.reload();
        }
        
        return response;
      };
      
      return () => {
        window.fetch = originalFetch;
      };
    }
  }, [isAuthenticated]);
"""

# Insert the interceptor immediately after `const [walletStatus, setWalletStatus] = useState({ address: null, balance: null });`
if "window.fetch = async (url, options = {})" not in content:
    content = content.replace(
        "const [walletStatus, setWalletStatus] = useState({ address: null, balance: null });",
        "const [walletStatus, setWalletStatus] = useState({ address: null, balance: null });\n" + interceptor_code
    )

with open(file_path, "w") as f:
    f.write(content)

print("App.jsx patched successfully with fetch interceptor!")
