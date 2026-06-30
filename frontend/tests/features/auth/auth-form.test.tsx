import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mockReplace = vi.fn();
const mockSearchParamsGet = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  useSearchParams: () => ({ get: mockSearchParamsGet }),
}));

const mockSetUser = vi.fn();

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: (selector: (s: any) => any) => selector({ setUser: mockSetUser }),
}));

vi.mock("@/services/auth.service", () => ({
  authService: {
    login: vi.fn(),
    register: vi.fn(),
  },
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
    button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: ({ mutationFn, onSuccess, onError }: any) => ({
    mutate: async (values: any) => {
      try {
        const data = await mutationFn(values);
        onSuccess?.(data);
      } catch (error) {
        onError?.(error);
      }
    },
    isPending: false,
  }),
}));

import { AuthForm } from "@/features/auth/auth-form";
import { authService } from "@/services/auth.service";
import { toast } from "sonner";

const mockAuthResponse = {
  access_token: "token",
  token_type: "bearer" as const,
  user: { id: 1, email: "test@example.com", full_name: "Test User" },
};

describe("AuthForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParamsGet.mockReturnValue(null);
  });

  describe("login mode", () => {
    it("renders sign-in form with email and password fields", () => {
      render(<AuthForm mode="login" />);

      expect(screen.getAllByText("Sign in").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByPlaceholderText("you@example.com")).toBeTruthy();
      expect(screen.getByPlaceholderText("Enter your password")).toBeTruthy();
      expect(screen.queryByPlaceholderText("Full name")).toBeNull();
    });

    it("calls authService.login on submit with valid data", async () => {
      vi.mocked(authService.login).mockResolvedValueOnce(mockAuthResponse);

      render(<AuthForm mode="login" />);

      await userEvent.type(screen.getByPlaceholderText("you@example.com"), "test@example.com");
      await userEvent.type(screen.getByPlaceholderText("Enter your password"), "MyStrongPass123!");
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        expect(authService.login).toHaveBeenCalledWith({
          email: "test@example.com",
          password: "MyStrongPass123!",
        });
      });
    });

    it("sets user and redirects to /dashboard on success", async () => {
      vi.mocked(authService.login).mockResolvedValueOnce(mockAuthResponse);

      render(<AuthForm mode="login" />);

      await userEvent.type(screen.getByPlaceholderText("you@example.com"), "test@example.com");
      await userEvent.type(screen.getByPlaceholderText("Enter your password"), "MyStrongPass123!");
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        expect(mockSetUser).toHaveBeenCalledWith(mockAuthResponse.user);
        expect(mockReplace).toHaveBeenCalledWith("/dashboard");
      });
    });

    it("shows toast error on failure", async () => {
      const error = new Error("Invalid credentials");
      vi.mocked(authService.login).mockRejectedValueOnce(error);

      render(<AuthForm mode="login" />);

      await userEvent.type(screen.getByPlaceholderText("you@example.com"), "test@example.com");
      await userEvent.type(screen.getByPlaceholderText("Enter your password"), "MyStrongPass123!");
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith("Invalid credentials");
      });
    });

    it("redirects to safe next param when present", async () => {
      mockSearchParamsGet.mockReturnValue("/opportunities");
      vi.mocked(authService.login).mockResolvedValueOnce(mockAuthResponse);

      render(<AuthForm mode="login" />);

      await userEvent.type(screen.getByPlaceholderText("you@example.com"), "test@example.com");
      await userEvent.type(screen.getByPlaceholderText("Enter your password"), "MyStrongPass123!");
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        expect(mockReplace).toHaveBeenCalledWith("/opportunities");
      });
    });

    it("renders link to register page", () => {
      render(<AuthForm mode="login" />);
      expect(screen.getByText("Create account").closest("a")).toHaveAttribute("href", "/register");
    });

    it("renders forgot password link", () => {
      render(<AuthForm mode="login" />);
      expect(screen.getByText("Forgot password?").closest("a")).toHaveAttribute("href", "/forgot-password");
    });
  });

  describe("register mode", () => {
    it("renders register form with full name field", () => {
      render(<AuthForm mode="register" />);

      expect(screen.getByText("Create account")).toBeTruthy();
      expect(screen.getByPlaceholderText("Full name")).toBeTruthy();
      expect(screen.getByPlaceholderText("you@example.com")).toBeTruthy();
      expect(screen.getByPlaceholderText("Enter your password")).toBeTruthy();
    });

    it("calls authService.register on submit", async () => {
      vi.mocked(authService.register).mockResolvedValueOnce(mockAuthResponse);

      render(<AuthForm mode="register" />);

      await userEvent.type(screen.getByPlaceholderText("Full name"), "Test User");
      await userEvent.type(screen.getByPlaceholderText("you@example.com"), "test@example.com");
      await userEvent.type(screen.getByPlaceholderText("Enter your password"), "MyStrongPass123!");
      fireEvent.click(screen.getByRole("button", { name: /register/i }));

      await waitFor(() => {
        expect(authService.register).toHaveBeenCalledWith({
          email: "test@example.com",
          password: "MyStrongPass123!",
          full_name: "Test User",
        });
      });
    });

    it("renders link to login page", () => {
      render(<AuthForm mode="register" />);
      expect(screen.getByText("Sign in").closest("a")).toHaveAttribute("href", "/login");
    });
  });
});
