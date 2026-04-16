package com.hmdp.mq;

import com.hmdp.HmDianPingApplication;
import com.hmdp.entity.VoucherOrder;
import com.hmdp.utils.RedisIdWorker;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

import javax.annotation.Resource;
import java.sql.Timestamp;
import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = HmDianPingApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
                "rocketmq.consumer.listeners[seckill-order-consumer-group][seckill-order-topic]=false"
        }
)
public class IdempotencyTest {

    private static final Long TEST_VOUCHER_ID = 20001L;
    private static final Long TEST_USER_ID = 900001L;
    private static final Integer INITIAL_STOCK = 5;

    @Resource
    private SeckillOrderConsumer consumer;

    @Resource
    private RedisIdWorker redisIdWorker;

    @Resource
    private JdbcTemplate jdbcTemplate;

    @Resource
    private StringRedisTemplate stringRedisTemplate;

    private Long testOrderId;

    @BeforeEach
    void setUp() {
        LocalDateTime now = LocalDateTime.now();
        Timestamp beginTime = Timestamp.valueOf(now.minusDays(1));
        Timestamp endTime = Timestamp.valueOf(now.plusDays(1));
        jdbcTemplate.update(
                "INSERT INTO tb_voucher " +
                        "(id, shop_id, title, sub_title, rules, pay_value, actual_value, type, status, create_time, update_time) " +
                        "VALUES (?, 1, 'Phase2幂等测试券', '重复消费集成测试', '仅用于Phase 2集成测试', 100, 100, 1, 1, NOW(), NOW()) " +
                        "ON DUPLICATE KEY UPDATE " +
                        "shop_id = VALUES(shop_id), " +
                        "title = VALUES(title), " +
                        "sub_title = VALUES(sub_title), " +
                        "rules = VALUES(rules), " +
                        "pay_value = VALUES(pay_value), " +
                        "actual_value = VALUES(actual_value), " +
                        "type = VALUES(type), " +
                        "status = VALUES(status), " +
                        "update_time = NOW()",
                TEST_VOUCHER_ID
        );
        jdbcTemplate.update(
                "INSERT INTO tb_seckill_voucher " +
                        "(voucher_id, stock, create_time, begin_time, end_time, update_time) " +
                        "VALUES (?, ?, NOW(), ?, ?, NOW()) " +
                        "ON DUPLICATE KEY UPDATE " +
                        "stock = VALUES(stock), " +
                        "begin_time = VALUES(begin_time), " +
                        "end_time = VALUES(end_time), " +
                        "update_time = NOW()",
                TEST_VOUCHER_ID, INITIAL_STOCK, beginTime, endTime
        );
        jdbcTemplate.update("DELETE FROM tb_voucher_order WHERE voucher_id = ? AND user_id = ?", TEST_VOUCHER_ID, TEST_USER_ID);
        stringRedisTemplate.opsForSet().remove("seckill:order:" + TEST_VOUCHER_ID, TEST_USER_ID.toString());
    }

    @AfterEach
    void tearDown() {
        jdbcTemplate.update("DELETE FROM tb_voucher_order WHERE voucher_id = ? AND user_id = ?", TEST_VOUCHER_ID, TEST_USER_ID);
        jdbcTemplate.update("UPDATE tb_seckill_voucher SET stock = ?, update_time = NOW() WHERE voucher_id = ?",
                INITIAL_STOCK, TEST_VOUCHER_ID);
        stringRedisTemplate.opsForSet().remove("seckill:order:" + TEST_VOUCHER_ID, TEST_USER_ID.toString());
    }

    @Test
    void shouldAckDuplicateMessageAndKeepSingleOrderRow() {
        VoucherOrder order = new VoucherOrder();
        testOrderId = redisIdWorker.nextId("order");
        order.setId(testOrderId);
        order.setUserId(TEST_USER_ID);
        order.setVoucherId(TEST_VOUCHER_ID);

        consumer.onMessage(order);
        long firstCountById = countById(testOrderId);
        long firstCountByUserVoucher = countByUserVoucher();

        consumer.onMessage(order);
        long secondCountById = countById(testOrderId);
        long secondCountByUserVoucher = countByUserVoucher();
        Integer stock = jdbcTemplate.queryForObject(
                "SELECT stock FROM tb_seckill_voucher WHERE voucher_id = ?",
                Integer.class,
                TEST_VOUCHER_ID
        );

        System.out.printf(
                "IdempotencyTest orderId=%d, firstCountById=%d, secondCountById=%d, firstCountByUserVoucher=%d, secondCountByUserVoucher=%d, stock=%d%n",
                testOrderId, firstCountById, secondCountById, firstCountByUserVoucher, secondCountByUserVoucher, stock
        );

        assertEquals(1L, firstCountById);
        assertEquals(1L, secondCountById);
        assertEquals(1L, firstCountByUserVoucher);
        assertEquals(1L, secondCountByUserVoucher);
        assertEquals(INITIAL_STOCK - 1, stock);
    }

    private long countById(Long orderId) {
        Long count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM tb_voucher_order WHERE id = ?",
                Long.class,
                orderId
        );
        return count == null ? 0L : count;
    }

    private long countByUserVoucher() {
        Long count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM tb_voucher_order WHERE user_id = ? AND voucher_id = ?",
                Long.class,
                TEST_USER_ID,
                TEST_VOUCHER_ID
        );
        return count == null ? 0L : count;
    }
}
